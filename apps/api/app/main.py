from __future__ import annotations

import json
import os
import re
import smtplib
import asyncio
import copy
import hashlib
import time
import uuid
from datetime import datetime, timedelta, timezone
from html import escape as html_escape
from io import BytesIO
from pathlib import Path
from email.message import EmailMessage
from typing import Annotated
from urllib.parse import urlparse

import boto3
import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageFilter, ImageOps
from starlette.datastructures import Headers

from brand.types import ImageInput
from valuation import ValuationConfig, ValuationService
from valuation.types import ValuationRequest

from .auth import AuthPrincipal, get_request_principal, require_clerk_user
from .db import Database, PersistedImage, utc_now_iso
from .deps import (
    get_db,
    get_gpt_item_profiler,
    get_settings,
    get_storage,
    get_valuation_service,
)
from .logging_utils import log_json
from .schemas import (
    AnalyzeResponse,
    AuthMeResponse,
    BrandOut,
    ClientStateResponse,
    ClientStateUpdateRequest,
    ConfirmPresignedImageUploadRequest,
    ConditionGrade,
    ConditionOut,
    HealthResponse,
    ListingCreateRequest,
    ListingResponse,
    OfferActionRequest,
    OfferCreateRequest,
    OfferResponse,
    OfferWithListingsResponse,
    ShippingLabelCreateRequest,
    ShippingQuoteResponse,
    PaymentMethodCreateRequest,
    PaymentMethodListResponse,
    PaymentMethodResponse,
    PresignImageUploadRequest,
    PresignImageUploadResponse,
    PresignedImageUploadSlot,
    StripeSetupCheckoutRequest,
    StripeSetupCheckoutResponse,
    StripeAttachPaymentMethodRequest,
    StripeSetupIntentResponse,
    SubscriptionActivateRequest,
    SubscriptionActivateResponse,
    TradeMatchListResponse,
    TradeMatchResponse,
    TradeMatchRunResponse,
    TradeMatchStatusUpdateRequest,
    UploadedImageOut,
    UploadImagesResponse,
    UserNotificationResponse,
    UserProfileQuizResponse,
    UserProfileQuizUpdateRequest,
    VersionResponse,
)
from .settings import Settings
from .storage import Storage, build_storage
from .trade_match_agent import build_trade_match_suggestions


app = FastAPI(title="ValueAI Fashion Analyzer", version="0.1.0")
API_REQUEST_SLOW_THRESHOLD_SECONDS = 5.0
SUBSCRIPTION_PLANS = {
    "free": {
        "label": "Free",
        "monthly_cents": 0,
        "annual_cents": 0,
    },
    "starter_15": {
        "label": "JOUFT $15 Plan",
        "monthly_cents": 1500,
        "annual_cents": 16200,
    },
    "pro_25": {
        "label": "JOUFT $25 Plan",
        "monthly_cents": 2500,
        "annual_cents": 27000,
    },
}


@app.middleware("http")
async def log_api_request_timing(request: Request, call_next):
    path = request.url.path
    should_log = path.startswith("/v1/")
    started = time.perf_counter()
    status_code = 500
    completed_logged = False
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception:
        duration_s = time.perf_counter() - started
        if should_log:
            duration_ms = round(duration_s * 1000, 2)
            log_json(
                "api_request_completed",
                method=request.method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
                ok=False,
            )
            if duration_s > API_REQUEST_SLOW_THRESHOLD_SECONDS:
                log_json(
                    "api_request_slow_alert",
                    method=request.method,
                    path=path,
                    status_code=status_code,
                    duration_ms=duration_ms,
                    threshold_ms=int(API_REQUEST_SLOW_THRESHOLD_SECONDS * 1000),
                    ok=False,
                )
            completed_logged = True
        raise
    finally:
        duration_s = time.perf_counter() - started
        if should_log and not completed_logged:
            duration_ms = round(duration_s * 1000, 2)
            log_json(
                "api_request_completed",
                method=request.method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
                ok=status_code < 500,
            )
            if duration_s > API_REQUEST_SLOW_THRESHOLD_SECONDS:
                log_json(
                    "api_request_slow_alert",
                    method=request.method,
                    path=path,
                    status_code=status_code,
                    duration_ms=duration_ms,
                    threshold_ms=int(API_REQUEST_SLOW_THRESHOLD_SECONDS * 1000),
                    ok=status_code < 500,
                )
_default_local_origins = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:5175",
    "http://127.0.0.1:5175",
}
_settings_for_cors = get_settings()
_configured_origins = {o.strip() for o in _settings_for_cors.cors_allow_origins.split(",") if o.strip()}
_cors_origins = sorted(_configured_origins | _default_local_origins)
_cors_origin_regex = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
# In local development, allow any browser origin so frontend can run on
# arbitrary hosts/ports (localhost, local network hostname/IP, tunnels).
if _settings_for_cors.app_env.lower() == "local":
    _cors_origin_regex = r"^https?://[a-zA-Z0-9.-]+(:\d+)?$"
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_origin_regex=_cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(STATIC_DIR)), name="ui")
ASSETS_DIR = STATIC_DIR / "assets"
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
_settings = get_settings()
if _settings.storage_backend == "local":
    _uploads_dir = Path(_settings.local_storage_dir) / "uploads"
    _uploads_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(_uploads_dir)), name="uploads")

VALID_CATEGORIES = {"clothes", "shoes", "handbag"}
VALID_CONDITION_GRADES = {
    "newwithtags": "NewWithTags",
    "newwithtag": "NewWithTags",
    "brandnewwithtags": "NewWithTags",
    "nwt": "NewWithTags",
    "new": "New",
    "likenew": "LikeNew",
}
CONDITION_SEVERITY_RANK = {"NewWithTags": 6, "New": 5, "LikeNew": 4}


def _trade_match_tolerance(value: float) -> tuple[float, float]:
    v = float(value or 0.0)
    if v <= 0:
        return 0.0, 0.0
    if v < 250:
        pct = 0.30
    elif v < 500:
        pct = 0.25
    elif v < 1000:
        pct = 0.20
    elif v < 1500:
        pct = 0.15
    elif v < 3000:
        pct = 0.12
    elif v < 5000:
        pct = 0.10
    elif v < 10000:
        pct = 0.075
    else:
        pct = 0.05
    tolerance = v * pct
    if v >= 10000:
        tolerance = min(tolerance, 1000.0)
    return tolerance, pct


def _normalize_size_token(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().casefold())


def _split_size_tokens(value: object) -> set[str]:
    if not isinstance(value, str):
        return set()
    tokens: set[str] = set()
    for part in re.split(r"[,\n;/|]+", value):
        token = _normalize_size_token(part)
        if token:
            tokens.add(token)
    return tokens


def _profile_size_preferences(profile: dict | None) -> dict[str, set[str]]:
    p = profile or {}
    clothes = set()
    for key in ("tops_size", "dresses_size", "bottoms_size"):
        clothes |= _split_size_tokens(p.get(key))
    shoes = _split_size_tokens(p.get("shoes_size"))
    return {"clothes": clothes, "shoes": shoes}


def _listing_matches_viewer_size_preferences(
    listing: dict,
    viewer_size_prefs: dict[str, set[str]],
) -> bool:
    category = str(listing.get("category") or "").strip().casefold()
    if category not in {"clothes", "shoes"}:
        return True
    listing_size = _normalize_size_token(listing.get("size"))
    if not listing_size:
        return False
    allowed = viewer_size_prefs.get(category) or set()
    if not allowed:
        return False
    return listing_size in allowed


def _sent_offer_match_pairs(db: Database, subject: str) -> set[tuple[str, str]]:
    """Return active marketplace target/offered-listing pairs already sent by this viewer."""
    active_statuses = {"pending", "accepted", "countered"}
    pairs: set[tuple[str, str]] = set()
    for offer in db.list_trade_offers_for_subject(subject, limit=200, status=None):
        if str(offer.get("from_subject") or "") != subject:
            continue
        if str(offer.get("status") or "").lower() not in active_statuses:
            continue
        target_id = str(offer.get("target_listing_id") or "").strip()
        offered_ids = [
            str(x).strip()
            for x in (offer.get("offered_listing_ids") or [])
            if isinstance(x, str) and str(x).strip()
        ]
        if not offered_ids and isinstance(offer.get("offered_listing_id"), str):
            offered_ids = [offer["offered_listing_id"].strip()]
        for offered_id in offered_ids:
            if target_id and offered_id:
                pairs.add((target_id, offered_id))
    return pairs


def _public_image_url_from_storage_uri(storage_uri: str, settings: Settings) -> str:
    if storage_uri.startswith("http://") or storage_uri.startswith("https://"):
        return storage_uri
    if storage_uri.startswith("s3://"):
        return storage_uri
    if settings.storage_backend == "local":
        marker = "/uploads/"
        norm = storage_uri.replace("\\", "/")
        idx = norm.find(marker)
        if idx >= 0:
            return f"/uploads/{norm[idx + len(marker):]}"
    return storage_uri


def _normalize_public_image_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    if s.startswith("http://") or s.startswith("https://"):
        parsed = urlparse(s)
        hostname = (parsed.hostname or "").lower()
        if parsed.path.startswith("/v1/images/") and (
            hostname.endswith(".elb.amazonaws.com")
            or hostname in {"jouft.com", "www.jouft.com", "api.jouft.com"}
        ):
            return parsed.path
        return s
    if s.startswith("/"):
        return s
    return None


def _image_url_dedupe_key(value: object) -> str:
    normalized = _normalize_public_image_url(value)
    return normalized or str(value or "").strip()


def _normalize_listing_media_for_storage(
    *,
    db: Database,
    image: str | None,
    images: list[object] | None,
    source_item_id: str | None,
) -> tuple[str | None, list[object]]:
    def resolve(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        s = value.strip()
        if not s:
            return None
        image_id = db.get_image_id_by_public_url(s, source_item_id)
        if image_id:
            return f"/v1/images/{image_id}"
        normalized_public_url = _normalize_public_image_url(s)
        if normalized_public_url:
            return normalized_public_url
        if s.startswith("s3://"):
            image_id = db.get_image_id_by_storage_uri(s)
            if image_id:
                return f"/v1/images/{image_id}"
            return None
        return None

    normalized_images: list[object] = []
    seen_image_keys: set[str] = set()
    if isinstance(images, list):
        for entry in images:
            if isinstance(entry, dict):
                original = resolve(entry.get("p_img") or entry.get("original_image") or entry.get("source_image"))
                display = resolve(entry.get("d_img") or entry.get("display_image") or entry.get("image") or original)
                key = _image_url_dedupe_key(display)
                if display and key not in seen_image_keys:
                    normalized_images.append({
                        "p_img": original or display,
                        "d_img": display,
                        "is_hero": bool(entry.get("is_hero")),
                    })
                    seen_image_keys.add(key)
                continue
            url = resolve(entry)
            key = _image_url_dedupe_key(url)
            if url and key not in seen_image_keys:
                normalized_images.append(url)
                seen_image_keys.add(key)

    normalized_image = resolve(image)
    normalized_image_key = _image_url_dedupe_key(normalized_image)
    if normalized_image and normalized_image_key not in seen_image_keys:
        normalized_images.insert(0, normalized_image)
        seen_image_keys.add(normalized_image_key)

    if not normalized_image and normalized_images:
        first = normalized_images[0]
        normalized_image = first.get("d_img") if isinstance(first, dict) else first

    return normalized_image, normalized_images


def _display_image_urls_from_storage_images(images: list[object] | None) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for entry in images or []:
        value = entry.get("d_img") if isinstance(entry, dict) else entry
        if not isinstance(value, str) or not value.strip():
            continue
        key = _image_url_dedupe_key(value)
        if key in seen:
            continue
        urls.append(value.strip())
        seen.add(key)
    return urls


def _same_listing_image_urls(left: list[str] | None, right: list[str] | None) -> bool:
    def normalize(values: list[str] | None) -> list[str]:
        return [str(value or "").strip() for value in (values or []) if str(value or "").strip()]

    return normalize(left) == normalize(right)


def _image_content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _profile_owner_display_name(db: Database, owner_subject: object, fallback: object = None) -> str:
    subject = str(owner_subject or "").strip()
    profile = db.get_user_profile_quiz(subject) if subject else None
    if profile:
        profile_name = " ".join(
            p for p in [profile.get("first_name"), profile.get("last_name")]
            if isinstance(p, str) and p.strip()
        ).strip()
        if profile_name:
            return profile_name
    fallback_name = str(fallback or "").strip()
    if fallback_name and fallback_name != subject and not fallback_name.lower().startswith("user_"):
        return fallback_name
    return "Member"


def _profile_subject_first_name(db: Database, owner_subject: object, fallback: object = None) -> str:
    subject = str(owner_subject or "").strip()
    profile = db.get_user_profile_quiz(subject) if subject else None
    if profile:
        first_name = profile.get("first_name")
        if isinstance(first_name, str) and first_name.strip():
            return first_name.strip()
    fallback_name = str(fallback or "").strip()
    if fallback_name and fallback_name != subject and not fallback_name.lower().startswith("user_"):
        return fallback_name.split()[0]
    return "Member"


def _hydrate_listing_owner_name(db: Database, record: dict) -> dict:
    if not isinstance(record, dict):
        return record
    record["owner_name"] = _profile_owner_display_name(
        db,
        record.get("owner_subject"),
        record.get("owner_name"),
    )
    return record


def _uploaded_image_urls_from_analysis(analysis: object) -> list[str]:
    if not isinstance(analysis, dict):
        return []
    uploaded = analysis.get("uploaded_images")
    if not isinstance(uploaded, list):
        return []
    urls: list[str] = []
    for entry in uploaded:
        if not isinstance(entry, dict):
            continue
        url = entry.get("image_url")
        if not isinstance(url, str):
            continue
        value = url.strip()
        normalized = _normalize_public_image_url(value)
        if normalized and normalized not in urls:
            urls.append(normalized)
    return urls


def _listing_storage_images(
    payload_images: list[str] | None,
    analysis: object,
    listed_images: list[object] | None = None,
) -> list[object]:
    explicit_listed_images: list[dict[str, object]] = []
    for entry in listed_images or []:
        if hasattr(entry, "model_dump"):
            entry = entry.model_dump()
        if not isinstance(entry, dict):
            continue
        original = entry.get("p_img") or entry.get("original_image") or entry.get("source_image")
        display = entry.get("d_img") or entry.get("display_image") or entry.get("image") or original
        if isinstance(display, str) and display.strip() and _normalize_public_image_url(display):
            explicit_listed_images.append({
                "p_img": original if isinstance(original, str) and original.strip() else display,
                "d_img": display,
                "is_hero": bool(entry.get("is_hero")),
            })
    if explicit_listed_images:
        return explicit_listed_images

    explicit_images = [
        url
        for url in (payload_images or [])
        if isinstance(url, str) and url.strip() and _normalize_public_image_url(url)
    ]
    if explicit_images:
        original_images = _uploaded_image_urls_from_analysis(analysis)
        return [
            {
                "p_img": original_images[idx] if idx < len(original_images) else url,
                "d_img": url,
                "is_hero": idx == 0,
            }
            for idx, url in enumerate(explicit_images)
        ]
    return _uploaded_image_urls_from_analysis(analysis)


def _uploaded_images_for_item(db: Database, item_id: str | None) -> list[dict]:
    if not item_id:
        return []
    uploaded: list[dict] = []
    for idx, record in enumerate(db.list_image_records_for_item(item_id, limit=20)):
        image_id = str(record.get("image_id") or "").strip()
        if not image_id:
            continue
        uploaded.append(
            {
                "image_id": image_id,
                "role_hint": record.get("role_hint") or ("full_item" if idx == 0 else "close_up"),
                "storage_uri": record.get("storage_uri") or "",
                "image_url": f"/v1/images/{image_id}",
            }
        )
    return uploaded


def _profile_description_from_analysis(response_payload: dict) -> tuple[str, str]:
    profile = response_payload.get("item_profile") if isinstance(response_payload.get("item_profile"), dict) else {}
    model_identification = profile.get("model_identification") if isinstance(profile.get("model_identification"), dict) else {}
    model_name = str(model_identification.get("name") or "").strip()
    attributes = model_identification.get("attributes")
    attribute_values = [str(a).strip() for a in attributes if isinstance(a, str) and a.strip()] if isinstance(attributes, list) else []
    profile_description = ""
    if model_name and attribute_values:
        profile_description = f"{model_name}. Key details: {', '.join(attribute_values[:6])}."
    elif model_name:
        profile_description = f"Pre-owned {model_name}."
    elif attribute_values:
        profile_description = f"Key details: {', '.join(attribute_values[:6])}."
    return model_name, profile_description


_DEFAULT_LISTING_TITLES = {"", "new listing", "unknown", "unknown unknown", "unclear", "n/a", "none"}


def _listing_title_from_analysis(
    current_title: object,
    *,
    model_name: str,
    profile: dict,
    brand: str,
    category: str,
) -> str:
    existing = str(current_title or "").strip()
    if existing.casefold() not in _DEFAULT_LISTING_TITLES:
        return existing

    normalized_brand = str(brand or "").strip()
    if normalized_brand.casefold() in {"", "unknown", "n/a", "none"}:
        normalized_brand = ""

    model = str(model_name or "").strip()
    if model.casefold() in _DEFAULT_LISTING_TITLES:
        model = ""
    unidentified_prefix = "unidentified "
    model_was_generic = model.casefold().startswith(unidentified_prefix)
    if model_was_generic:
        model = model[len(unidentified_prefix):].strip()

    if model:
        if model_was_generic and normalized_brand and not model.casefold().startswith(normalized_brand.casefold()):
            return f"{normalized_brand} {model}".strip()
        return model

    shipping_profile = profile.get("shipping_profile") if isinstance(profile.get("shipping_profile"), dict) else {}
    item_type = str(shipping_profile.get("item_type") or "").strip()
    if not item_type or item_type.casefold() in {"unknown", "item"}:
        item_type = str(category or "").strip()
    if item_type.casefold() in {"", "unknown", "clothes", "accessories"}:
        item_type = "item"
    if normalized_brand:
        return f"{normalized_brand} {item_type}".strip()
    return "New listing"


def _normalize_condition_for_analysis_reuse(value: object) -> str:
    normalized = str(value or "").strip().replace("-", "").replace("_", "").replace(" ", "").casefold()
    return VALID_CONDITION_GRADES.get(normalized, "")


def _cached_analysis_is_strong_enough_for_reuse(response_payload: dict) -> bool:
    brand = response_payload.get("brand") if isinstance(response_payload.get("brand"), dict) else {}
    brand_name = str(brand.get("name") or "").strip()
    brand_confidence = float(brand.get("confidence") or 0)
    profile = response_payload.get("item_profile") if isinstance(response_payload.get("item_profile"), dict) else {}
    model = profile.get("model_identification") if isinstance(profile.get("model_identification"), dict) else {}
    model_name = str(model.get("name") or "").strip()
    unknown_values = {"", "unknown", "unknown unknown", "n/a", "none"}
    if brand_name.casefold() in unknown_values:
        return False
    if model_name.casefold() in unknown_values:
        return False
    return brand_confidence >= 0.7


def _reuse_recent_analysis_for_listing(
    *,
    db: Database,
    listing_id: str,
    owner_subject: str,
    current: dict,
) -> dict | None:
    source_item_id = str(current.get("source_item_id") or "").strip()
    if not source_item_id:
        return None
    image_hashes = db.list_image_content_hashes_for_item(source_item_id, limit=20)
    if not image_hashes:
        return None
    cached = db.find_recent_analysis_by_image_hashes(
        image_hashes,
        limit=50,
        owner_subject=owner_subject,
    )
    if not cached or not isinstance(cached.get("response"), dict):
        return None
    if not _cached_analysis_is_strong_enough_for_reuse(cached["response"]):
        brand = cached["response"].get("brand") if isinstance(cached["response"].get("brand"), dict) else {}
        log_json(
            "listing_analysis_reuse_skipped_weak_cached_analysis",
            listing_id=listing_id,
            actor=owner_subject,
            source_item_id=source_item_id,
            source_analysis_id=cached.get("analysis_id"),
            cached_brand=brand.get("name"),
            cached_brand_confidence=brand.get("confidence"),
            image_count=len(image_hashes),
        )
        return None
    cached_condition = _normalize_condition_for_analysis_reuse(cached["response"].get("user_condition"))
    current_condition = _normalize_condition_for_analysis_reuse(current.get("condition"))
    if not cached_condition or not current_condition or cached_condition != current_condition:
        log_json(
            "listing_analysis_reuse_skipped_condition_mismatch",
            listing_id=listing_id,
            actor=owner_subject,
            source_item_id=source_item_id,
            source_analysis_id=cached.get("analysis_id"),
            cached_condition=cached_condition or None,
            current_condition=current_condition or None,
            image_count=len(image_hashes),
        )
        return None
    response_payload = copy.deepcopy(cached["response"])
    response_payload["item_id"] = source_item_id
    uploaded_images = _uploaded_images_for_item(db, source_item_id)
    if uploaded_images:
        response_payload["uploaded_images"] = uploaded_images
    debug_payload = response_payload.get("debug") if isinstance(response_payload.get("debug"), dict) else {}
    debug_payload["analysis_reuse"] = {
        "reused": True,
        "source_analysis_id": cached.get("analysis_id"),
        "source_item_id": cached.get("item_id"),
        "matched_image_count": len(image_hashes),
    }
    response_payload["debug"] = debug_payload

    profile = response_payload.get("item_profile") if isinstance(response_payload.get("item_profile"), dict) else {}
    model_name, profile_description = _profile_description_from_analysis(response_payload)
    brand = str(response_payload.get("brand", {}).get("name") or current.get("brand") or "unknown")
    condition = str(response_payload.get("user_condition") or current.get("condition") or "LikeNew")
    resolved_category = str(response_payload.get("category") or current.get("category") or "handbag")
    valuation = response_payload.get("valuation") if isinstance(response_payload.get("valuation"), dict) else {}
    estimated_value = float(valuation.get("estimated_value") or current.get("estimated_value") or 0)
    image_urls = [entry["image_url"] for entry in uploaded_images if isinstance(entry.get("image_url"), str)]
    if not image_urls:
        existing_images = current.get("images") if isinstance(current.get("images"), list) else []
        image_urls = [url for url in existing_images if isinstance(url, str) and url.strip()]
    if not image_urls and isinstance(current.get("image"), str) and current.get("image"):
        image_urls = [str(current["image"])]
    title = _listing_title_from_analysis(
        current.get("title"),
        model_name=model_name,
        profile=profile,
        brand=brand,
        category=resolved_category,
    )
    description = str(current.get("description") or "").strip() or profile_description
    db.update_listing(
        listing_id=listing_id,
        owner_subject=owner_subject,
        title=title or "New listing",
        mode="trade",
        category=resolved_category,
        brand=brand,
        condition=condition,
        size=current.get("size"),
        estimated_value=estimated_value,
        city=str(current.get("city") or "Your area"),
        image=image_urls[0] if image_urls else None,
        images=image_urls,
        description=description,
        wants=str(current.get("wants") or "Open to similar-value offers"),
        tags=[condition, brand, "trade"],
        source_item_id=source_item_id,
        analysis=response_payload,
        status="Review",
    )
    log_json(
        "listing_analysis_reused",
        listing_id=listing_id,
        actor=owner_subject,
        item_id=source_item_id,
        source_analysis_id=cached.get("analysis_id"),
        source_item_id=cached.get("item_id"),
        image_count=len(image_hashes),
    )
    return {
        "title": title or "New listing",
        "category": resolved_category,
        "brand": brand,
        "condition": condition,
        "estimated_value": estimated_value,
        "image": image_urls[0] if image_urls else None,
        "images": image_urls,
        "description": description,
        "tags": [condition, brand, "trade"],
        "source_item_id": source_item_id,
        "analysis": response_payload,
        "status": "Review",
    }


def _presign_s3_uri(storage_uri: str, settings: Settings) -> str | None:
    if not storage_uri.startswith("s3://"):
        return None
    parsed = urlparse(storage_uri)
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    if not bucket or not key:
        return None
    session = boto3.session.Session()
    client = session.client(
        "s3",
        region_name=settings.s3_region,
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
    )
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=900,
    )


def _stream_s3_uri(storage_uri: str, settings: Settings) -> StreamingResponse | None:
    if not storage_uri.startswith("s3://"):
        return None
    parsed = urlparse(storage_uri)
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    if not bucket or not key:
        return None
    session = boto3.session.Session()
    client = session.client(
        "s3",
        region_name=settings.s3_region,
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
    )
    try:
        obj = client.get_object(Bucket=bucket, Key=key)
    except Exception:
        return None
    body = obj.get("Body")
    content_type = obj.get("ContentType") or "application/octet-stream"
    if body is None:
        return None
    return StreamingResponse(
        body.iter_chunks(chunk_size=64 * 1024),
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )


def _read_storage_uri_bytes(storage_uri: str, settings: Settings) -> tuple[bytes, str]:
    if storage_uri.startswith("http://") or storage_uri.startswith("https://"):
        with httpx.Client(timeout=20) as client:
            resp = client.get(storage_uri)
            resp.raise_for_status()
            return resp.content, resp.headers.get("content-type") or "image/jpeg"

    if storage_uri.startswith("s3://"):
        parsed = urlparse(storage_uri)
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        if not bucket or not key:
            raise FileNotFoundError("invalid s3 image uri")
        session = boto3.session.Session()
        client = session.client(
            "s3",
            region_name=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
        )
        obj = client.get_object(Bucket=bucket, Key=key)
        return obj["Body"].read(), obj.get("ContentType") or "image/jpeg"

    path = Path(storage_uri)
    candidate_paths = [path]
    if not path.is_absolute():
        base = Path(settings.local_storage_dir).resolve().parent
        candidate_paths.append((base / path).resolve())
        candidate_paths.append((Path(settings.local_storage_dir).resolve() / path).resolve())
    for candidate in candidate_paths:
        if candidate.exists():
            suffix = candidate.suffix.lower()
            content_type = "image/png" if suffix == ".png" else "image/webp" if suffix == ".webp" else "image/jpeg"
            return candidate.read_bytes(), content_type
    raise FileNotFoundError("image not found")


def _image_file_from_listing_url(
    *,
    db: Database,
    settings: Settings,
    url: str,
    index: int,
    source_item_id: str | None = None,
) -> dict[str, object] | None:
    image_id = db.get_image_id_by_public_url(url, source_item_id)
    if not image_id:
        return None
    storage_uri = db.get_image_storage_uri(image_id)
    if not storage_uri:
        return None
    data, content_type = _read_storage_uri_bytes(storage_uri, settings)
    ext = ".png" if "png" in content_type else ".webp" if "webp" in content_type else ".jpg"
    return {
        "filename": f"listing-image-{index + 1}{ext}",
        "content_type": content_type,
        "data": data,
        "source_url": f"/v1/images/{image_id}",
    }


def _mark_listing_analysis_failed(db: Database, listing: dict | None, owner_subject: str) -> None:
    if not listing:
        return
    image_urls = listing.get("images") if isinstance(listing.get("images"), list) else []
    try:
        db.update_listing(
            listing_id=str(listing.get("listing_id") or ""),
            owner_subject=owner_subject,
            title=str(listing.get("title") or "New listing"),
            mode="trade",
            category=str(listing.get("category") or "handbag"),
            brand=str(listing.get("brand") or "unknown"),
            condition=str(listing.get("condition") or "LikeNew"),
            size=listing.get("size"),
            estimated_value=float(listing.get("estimated_value") or 0),
            city=str(listing.get("city") or "Your area"),
            image=str(listing.get("image") or "") or None,
            images=image_urls,
            description=str(listing.get("description") or ""),
            wants=str(listing.get("wants") or "Open to similar-value offers"),
            tags=["Analysis failed"],
            source_item_id=listing.get("source_item_id"),
            analysis=listing.get("analysis"),
            status="AnalysisFailed",
        )
    except Exception as exc:
        log_json(
            "listing_analysis_failed_status_update_error",
            listing_id=listing.get("listing_id"),
            actor=owner_subject,
            error=str(exc),
        )


def _collect_listing_analysis_files(
    *,
    db: Database,
    settings: Settings,
    listing: dict,
    image_urls: list[str] | None = None,
) -> list[dict[str, object]]:
    raw_urls = image_urls if image_urls is not None else []
    if not raw_urls:
        images = listing.get("images") if isinstance(listing.get("images"), list) else []
        raw_urls = [str(url).strip() for url in images if isinstance(url, str) and url.strip()]
        image = listing.get("image")
        if isinstance(image, str) and image.strip() and image.strip() not in raw_urls:
            raw_urls.insert(0, image.strip())
    source_item_id = str(listing.get("source_item_id") or "").strip() or None
    files: list[dict[str, object]] = []
    for idx, image_url in enumerate(raw_urls):
        try:
            resolved = _image_file_from_listing_url(
                db=db,
                settings=settings,
                url=image_url,
                index=idx,
                source_item_id=source_item_id,
            )
        except Exception as exc:
            log_json(
                "listing_analysis_image_resolve_error",
                listing_id=listing.get("listing_id"),
                image_url=image_url,
                error=str(exc),
            )
            resolved = None
        if resolved:
            files.append(resolved)
    deduped_files: list[dict[str, object]] = []
    seen_signatures: set[tuple[str, int]] = set()
    for entry in files:
        data = entry.get("data")
        if not isinstance(data, bytes):
            continue
        signature = (str(entry.get("filename") or ""), len(data))
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        deduped_files.append(entry)
    return deduped_files[: settings.max_images_per_request]


def _remove_background_with_photoroom(raw: bytes, content_type: str, settings: Settings) -> tuple[bytes, str, dict[str, object]]:
    api_key = (settings.photoroom_api_key or "").strip()
    debug: dict[str, object] = {
        "attempted": bool(settings.image_staging_photoroom_enabled and api_key),
        "status_code": None,
        "reason": None,
        "error": None,
        "endpoint": settings.photoroom_segment_url,
    }
    if not settings.image_staging_photoroom_enabled:
        return raw, content_type, {**debug, "reason": "disabled"}
    if not api_key:
        return raw, content_type, {**debug, "reason": "api_key_missing"}

    output_format = (settings.photoroom_output_format or "jpg").strip().lower()
    if output_format == "jpeg":
        output_format = "jpg"
    if output_format not in {"jpg", "png", "webp"}:
        output_format = "jpg"
    output_content_type = {
        "jpg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }[output_format]
    filename_ext = "jpg" if output_format == "jpg" else output_format
    data = {
        "format": output_format,
        "size": (settings.photoroom_output_size or "full").strip() or "full",
        "crop": "false",
        "despill": "false",
    }
    bg_color = (settings.photoroom_background_color or "").strip()
    if bg_color:
        data["bg_color"] = bg_color

    try:
        with httpx.Client(timeout=settings.photoroom_timeout_s) as client:
            response = client.post(
                settings.photoroom_segment_url,
                headers={"x-api-key": api_key},
                data=data,
                files={"image_file": (f"upload.{filename_ext}", raw, content_type or "image/jpeg")},
            )
        debug["status_code"] = response.status_code
        response.raise_for_status()
        processed = response.content
        with Image.open(BytesIO(processed)) as result:
            result.verify()
        return processed, output_content_type, {
            **debug,
            "reason": "success",
            "format": output_format,
            "background_color": bg_color or None,
            "size": data["size"],
            "synthetic_shadow": False,
        }
    except Exception as exc:
        return raw, content_type, {
            **debug,
            "reason": "exception",
            "error": str(exc)[:500],
        }


def _apply_exif_orientation(raw: bytes, content_type: str) -> tuple[bytes, str, bool]:
    try:
        with Image.open(BytesIO(raw)) as src:
            orientation = src.getexif().get(274)
            if not orientation or orientation == 1:
                return raw, content_type, False
            transposed = ImageOps.exif_transpose(src)
            output_type = content_type or Image.MIME.get(src.format or "", "image/jpeg")
            output_type = output_type.lower()
            out = BytesIO()
            if output_type == "image/png":
                transposed.save(out, format="PNG")
                return out.getvalue(), "image/png", True
            if output_type == "image/webp":
                transposed.save(out, format="WEBP", quality=95)
                return out.getvalue(), "image/webp", True
            transposed.convert("RGB").save(out, format="JPEG", quality=95, optimize=True)
            return out.getvalue(), "image/jpeg", True
    except Exception:
        return raw, content_type, False


def _prepare_uploaded_image_for_storage(raw: bytes, content_type: str) -> tuple[bytes, str, dict[str, object]]:
    oriented_raw, oriented_content_type, orientation_applied = _apply_exif_orientation(raw, content_type or "image/jpeg")
    return oriented_raw, oriented_content_type, {
        "applied": orientation_applied,
        "provider": "exif_orientation",
        "exif_orientation_applied": orientation_applied,
        "background_staging": "deferred",
    }


def _stage_item_image(raw: bytes, content_type: str, settings: Settings) -> tuple[bytes, str, dict[str, object]]:
    if not settings.image_staging_enabled:
        return raw, content_type, {"applied": False, "reason": "disabled"}
    oriented_raw, oriented_content_type, orientation_applied = _apply_exif_orientation(raw, content_type or "image/jpeg")
    try:
        with Image.open(BytesIO(oriented_raw)) as src:
            src_rgba = src.convert("RGBA")
    except Exception:
        return raw, content_type, {"applied": False, "reason": "open_failed", "exif_orientation_applied": orientation_applied}

    photoroom_raw, photoroom_content_type, photoroom_debug = _remove_background_with_photoroom(oriented_raw, oriented_content_type, settings)
    if photoroom_debug.get("reason") == "success":
        return photoroom_raw, photoroom_content_type, {
            "applied": True,
            "provider": "photoroom_remove_background",
            "synthetic_shadow": False,
            "exif_orientation_applied": orientation_applied,
            "photoroom": photoroom_debug,
        }

    # Try Gemini image-edit next (white background), fallback to local rembg pipeline.
    gemini_stage_debug: dict[str, object] = {
        "attempted": bool(settings.image_staging_gemini_enabled and settings.gemini_api_key),
        "status_code": None,
        "reason": None,
        "error": None,
        "model": settings.image_staging_imagen_model,
    }
    if settings.image_staging_gemini_enabled and settings.gemini_api_key:
        try:
            from google import genai  # type: ignore
            from google.genai import types  # type: ignore

            model = settings.image_staging_imagen_model.strip() or "imagen-3.0-capability-001"
            if settings.image_staging_vertexai_enabled:
                if not settings.gcp_project_id:
                    raise RuntimeError("gcp_project_id_missing_for_vertexai")
                client = genai.Client(
                    vertexai=True,
                    project=settings.gcp_project_id,
                    location=settings.gcp_location or "us-central1",
                )
            else:
                client = genai.Client(api_key=settings.gemini_api_key)
            base_img = Image.open(BytesIO(oriented_raw)).convert("RGB")
            raw_ref = types.RawReferenceImage(
                reference_id=1,
                reference_image=base_img,
            )
            mask_ref = types.MaskReferenceImage(
                reference_id=2,
                reference_image=None,
                config=types.MaskReferenceConfig(mask_mode="MASK_MODE_BACKGROUND"),
            )
            result = client.models.generate_images(
                model=model,
                prompt=(
                    "Place the product on a clean, solid, pure white background (#FFFFFF). "
                    "Preserve the product pixels and details exactly. Do not add generated shadows, reflections, relighting, or styling."
                ),
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    output_mime_type="image/jpeg",
                    reference_images=[raw_ref, mask_ref],
                    edit_config=types.EditImageConfig(edit_mode="EDIT_MODE_BGSWAP"),
                ),
            )
            generated = getattr(result, "generated_images", None)
            if isinstance(generated, list) and generated:
                first = generated[0]
                img_obj = getattr(first, "image", None)
                if img_obj is not None:
                    out = BytesIO()
                    img_obj.save(out, format="JPEG", quality=92, optimize=True)
                    return out.getvalue(), "image/jpeg", {
                        "applied": True,
                        "provider": "imagen_background_edit",
                        "used_rembg": False,
                        "rembg_effective": False,
                        "forced_padding": False,
                        "synthetic_shadow": False,
                        "exif_orientation_applied": orientation_applied,
                        "photoroom": photoroom_debug,
                        "gemini_edit": {**gemini_stage_debug, "reason": "success"},
                    }
            gemini_stage_debug["reason"] = "no_generated_images"
            gemini_stage_debug["status_code"] = 200
        except Exception as exc:
            gemini_stage_debug["reason"] = "exception"
            gemini_stage_debug["error"] = str(exc)[:500]

    if not settings.condition_rembg_enabled:
        return oriented_raw, oriented_content_type, {
            "applied": False,
            "provider": None,
            "reason": "no_staging_provider_succeeded",
            "synthetic_shadow": False,
            "exif_orientation_applied": orientation_applied,
            "photoroom": photoroom_debug,
            "gemini_edit": gemini_stage_debug,
        }

    fg = src_rgba
    used_rembg = False
    rembg_effective = False
    try:
        from rembg import remove  # type: ignore

        removed = remove(
            oriented_raw,
            alpha_matting=True,
            alpha_matting_foreground_threshold=245,
            alpha_matting_background_threshold=10,
            alpha_matting_erode_size=8,
        )
        with Image.open(BytesIO(removed)) as rembg_img:
            fg = rembg_img.convert("RGBA")
        alpha = fg.split()[-1]
        coverage = sum(1 for px in alpha.getdata() if px > 20) / max(fg.size[0] * fg.size[1], 1)
        rembg_effective = coverage < 0.95
        if not rembg_effective:
            # Fallback: ask rembg for a raw mask and apply aggressive thresholding.
            mask_bytes = remove(oriented_raw, only_mask=True)
            with Image.open(BytesIO(mask_bytes)) as m:
                mask = ImageOps.autocontrast(m.convert("L"))
            mask = mask.point(lambda p: 255 if p >= 140 else 0)
            mask = mask.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.2))
            candidate = src_rgba.copy()
            candidate.putalpha(mask)
            alpha2 = candidate.split()[-1]
            coverage2 = sum(1 for px in alpha2.getdata() if px > 20) / max(candidate.size[0] * candidate.size[1], 1)
            if coverage2 < coverage:
                fg = candidate
                rembg_effective = coverage2 < 0.95
        used_rembg = True
    except Exception:
        fg = src_rgba

    w, h = fg.size
    grad = Image.linear_gradient("L").resize((w, h))
    top = Image.new("RGBA", (w, h), (252, 252, 253, 255))
    bottom = Image.new("RGBA", (w, h), (225, 227, 230, 255))
    bg = Image.composite(bottom, top, grad)

    alpha = fg.split()[-1]
    bbox = alpha.getbbox()
    if bbox:
        item = fg.crop(bbox)
        iw, ih = item.size
        original_fill_ratio = (iw * ih) / max(w * h, 1)
        # If item already fills almost entire frame, force more padding so staging is visible.
        target_fill = 0.62 if original_fill_ratio > 0.78 else 0.78
        max_w = int(w * target_fill)
        max_h = int(h * target_fill)
        scale = min(max_w / max(iw, 1), max_h / max(ih, 1), 1.35)
        nw = max(1, int(iw * scale))
        nh = max(1, int(ih * scale))
        item = item.resize((nw, nh), Image.Resampling.LANCZOS)

        x = (w - nw) // 2
        y = (h - nh) // 2
        bg.alpha_composite(item, (x, y))
    else:
        bg.alpha_composite(fg, (0, 0))

    out = BytesIO()
    bg.convert("RGB").save(out, format="JPEG", quality=92, optimize=True)
    return out.getvalue(), "image/jpeg", {
        "applied": True,
        "used_rembg": used_rembg,
        "rembg_effective": rembg_effective,
        "forced_padding": True,
        "synthetic_shadow": False,
        "exif_orientation_applied": orientation_applied,
        "photoroom": photoroom_debug,
        "gemini_edit": gemini_stage_debug,
    }


def infer_category_from_item_profile(item_profile: dict[str, object] | None) -> str | None:
    if not isinstance(item_profile, dict):
        return None
    explicit_category = item_profile.get("category")
    if isinstance(explicit_category, str):
        normalized = explicit_category.strip().casefold()
        if normalized == "handbags":
            normalized = "handbag"
        if normalized in VALID_CATEGORIES:
            return normalized
    model_identification = item_profile.get("model_identification")
    if not isinstance(model_identification, dict):
        return None

    text_parts: list[str] = []
    name = model_identification.get("name")
    if isinstance(name, str):
        text_parts.append(name)
    attributes = model_identification.get("attributes")
    if isinstance(attributes, list):
        text_parts.extend(attr for attr in attributes if isinstance(attr, str))
    if not text_parts:
        return None

    text = " ".join(text_parts).casefold()
    shoes_terms = ("shoe", "boot", "sandal", "sneaker", "heel", "pump", "loafer", "mule")
    handbag_terms = ("handbag", "bag", "purse", "tote", "satchel", "crossbody", "clutch")
    clothes_terms = ("dress", "jacket", "coat", "shirt", "top", "jeans", "pants", "skirt", "blouse", "sweater")

    if any(term in text for term in shoes_terms):
        return "shoes"
    if any(term in text for term in handbag_terms):
        return "handbag"
    if any(term in text for term in clothes_terms):
        return "clothes"
    return None


def infer_brand_from_item_profile(item_profile: dict[str, object] | None) -> tuple[str | None, float | None, str | None]:
    if not isinstance(item_profile, dict):
        return None, None, None
    candidate_brand = item_profile.get("candidate_brand")
    if not isinstance(candidate_brand, str):
        return None, None, None
    brand = candidate_brand.strip()
    if not brand:
        return None, None, None
    confidence = item_profile.get("confidence")
    try:
        conf = max(0.0, min(float(confidence), 1.0))
    except Exception:
        conf = None
    return brand, conf, "gpt_item_profile"


def _coerce_positive_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        num = float(value)
        return num if num > 0 else None
    if isinstance(value, str):
        try:
            num = float(value.strip())
            return num if num > 0 else None
        except Exception:
            return None
    return None


def _extract_prices_from_text(value: object) -> list[float]:
    if not isinstance(value, str):
        return []
    nums = re.findall(r"\$?\s*(\d{1,6}(?:,\d{3})*(?:\.\d{1,2})?)", value)
    out: list[float] = []
    for n in nums:
        try:
            v = float(n.replace(",", ""))
            if v > 0:
                out.append(v)
        except Exception:
            continue
    return out


def _extract_retail_prices_from_text(value: object) -> list[float]:
    if not isinstance(value, str):
        return []
    patterns = [
        r"retail(?:\s+(?:price|value|reference|msrp))?[^$]{0,80}\$\s*(\d{1,6}(?:,\d{3})*(?:\.\d{1,2})?)",
        r"\$\s*(\d{1,6}(?:,\d{3})*(?:\.\d{1,2})?)[^.\n]{0,80}\bretail\b",
    ]
    values: list[float] = []
    for pattern in patterns:
        for match in re.findall(pattern, value, flags=re.IGNORECASE):
            try:
                price = float(str(match).replace(",", ""))
            except Exception:
                continue
            if price > 0:
                values.append(price)
    return values


def _retail_to_resale_factor_for_category(category: object) -> float:
    category_key = str(category or "").strip().casefold()
    if category_key == "handbag":
        return 0.88
    if category_key == "shoes":
        return 0.80
    if category_key == "clothes":
        return 0.72
    return 0.80


def _condition_multiplier_for_retail_fallback(condition_grade: str | None) -> float:
    condition_key = str(condition_grade or "").strip()
    return {
        "NewWithTags": 1.10,
        "New": 1.00,
        "LikeNew": 0.90,
        "Good": 0.75,
        "Fair": 0.55,
        "Poor": 0.35,
    }.get(condition_key, 0.90)


def _visual_condition_pricing_multiplier(item_profile: dict[str, object]) -> tuple[float, dict[str, object]]:
    assessment = item_profile.get("visual_condition_assessment")
    if not isinstance(assessment, dict):
        return 1.0, {"applied": False}
    pricing_tier = str(assessment.get("pricing_tier") or "").strip().casefold()
    wear_level = str(assessment.get("wear_level") or "").strip().casefold()
    box_included = str(assessment.get("box_included") or "").strip().casefold()
    dust_bag_included = str(assessment.get("dust_bag_included") or "").strip().casefold()
    new_in_box_signal = str(assessment.get("new_in_box_signal") or "").strip().casefold()
    try:
        confidence = max(0.0, min(float(assessment.get("confidence")), 1.0))
    except Exception:
        confidence = 0.0

    multiplier = 1.0
    reasons: list[str] = []
    if confidence >= 0.55 and pricing_tier == "new_in_box":
        multiplier = 1.18
        reasons.append("new_in_box_pricing_tier")
    elif confidence >= 0.55 and pricing_tier == "pristine":
        multiplier = 1.10
        reasons.append("pristine_pricing_tier")

    if confidence >= 0.55 and wear_level == "pristine":
        multiplier = max(multiplier, 1.08)
        reasons.append("pristine_wear_level")
    if confidence >= 0.55 and box_included == "yes":
        multiplier += 0.04
        reasons.append("box_included")
    if confidence >= 0.55 and dust_bag_included == "yes":
        multiplier += 0.03
        reasons.append("dust_bag_included")
    if confidence >= 0.55 and new_in_box_signal == "yes":
        multiplier = max(multiplier, 1.18)
        reasons.append("new_in_box_signal")

    multiplier = min(multiplier, 1.18)
    if multiplier <= 1.0:
        return 1.0, {
            "applied": False,
            "pricing_tier": pricing_tier or "unclear",
            "confidence": round(confidence, 3),
        }
    return multiplier, {
        "applied": True,
        "multiplier": round(multiplier, 3),
        "pricing_tier": pricing_tier,
        "wear_level": wear_level,
        "box_included": box_included,
        "dust_bag_included": dust_bag_included,
        "new_in_box_signal": new_in_box_signal,
        "confidence": round(confidence, 3),
        "reasons": list(dict.fromkeys(reasons)),
        "evidence": assessment.get("evidence") if isinstance(assessment.get("evidence"), list) else [],
    }


def _select_breakdown_row(
    breakdown: object,
    *,
    condition_grade: str | None,
) -> tuple[float | None, float | None, float | None, str]:
    if not isinstance(breakdown, list):
        return None, None, None, "default"

    target = (condition_grade or "").strip().casefold()
    rows = [r for r in breakdown if isinstance(r, dict)]
    if not rows:
        return None, None, None, "default"

    def score(label: str) -> int:
        lbl = label.casefold()
        if target == "newwithtags":
            if "current-season" in lbl or "current season" in lbl:
                return 105
            if "new with tags" in lbl or "nwt" in lbl or "brand new with tags" in lbl:
                return 100
            if "brand new" in lbl or "tags" in lbl:
                return 95
            if "new" in lbl or "pristine" in lbl:
                return 85
        if target == "new":
            if "original retail" in lbl:
                return 40
            if "high-end" in lbl or "excellent" in lbl or "new" in lbl or "pristine" in lbl:
                return 90
        if target == "likenew":
            if "high-end" in lbl or "excellent" in lbl or "like" in lbl or "pristine" in lbl:
                return 100
            if "good" in lbl or "pre-owned" in lbl:
                return 70
        if target == "good":
            if "good" in lbl or "pre-owned" in lbl:
                return 100
            if "excellent" in lbl or "high-end" in lbl:
                return 70
        if target in {"fair", "poor"}:
            if "good" in lbl or "pre-owned" in lbl:
                return 90
            if "excellent" in lbl or "high-end" in lbl:
                return 60
        if "default" in lbl:
            return 50
        return 10

    best = max(rows, key=lambda r: score(str(r.get("label") or "")))
    label = str(best.get("label") or "default")
    est = _coerce_positive_float(best.get("estimated_price"))
    low = _coerce_positive_float(best.get("range_low"))
    high = _coerce_positive_float(best.get("range_high"))
    if est is None:
        values = _extract_prices_from_text(best.get("rationale"))
        if len(values) >= 2:
            low = low or min(values[0], values[1])
            high = high or max(values[0], values[1])
            est = round((low + high) / 2.0, 2) if low and high else None
        elif len(values) == 1:
            est = values[0]
    if est is None and low is not None and high is not None:
        est = round((low + high) / 2.0, 2)
    return est, low, high, label


def valuation_from_gpt_item_profile(
    item_profile: dict[str, object] | None,
    *,
    default_currency: str,
    condition_grade: str | None = None,
) -> dict[str, object] | None:
    if not isinstance(item_profile, dict):
        return None

    resale = item_profile.get("resale_price_estimate")
    retail = item_profile.get("retail_price_estimate")
    resale_breakdown = item_profile.get("resale_price_breakdown")
    estimated_value = None
    range_low = None
    range_high = None
    pricing_row_label = "resale_price_estimate"
    if isinstance(resale, dict):
        estimated_value = _coerce_positive_float(resale.get("estimated_price"))
    breakdown_estimated_value, breakdown_range_low, breakdown_range_high, breakdown_row_label = _select_breakdown_row(
        resale_breakdown,
        condition_grade=condition_grade,
    )
    if (
        str(condition_grade or "").strip().casefold() == "newwithtags"
        and breakdown_estimated_value is not None
        and (estimated_value is None or breakdown_estimated_value > estimated_value)
    ):
        estimated_value = breakdown_estimated_value
        range_low = breakdown_range_low
        range_high = breakdown_range_high
        pricing_row_label = breakdown_row_label
    if estimated_value is None:
        estimated_value = breakdown_estimated_value
        range_low = breakdown_range_low
        range_high = breakdown_range_high
        pricing_row_label = breakdown_row_label

    retail_reference = _coerce_positive_float(retail.get("estimated_price")) if isinstance(retail, dict) else None
    retail_derived = False
    visual_condition_adjustment: dict[str, object] = {"applied": False}
    if estimated_value is None and retail_reference is not None:
        factor = _retail_to_resale_factor_for_category(item_profile.get("category"))
        condition_multiplier = _condition_multiplier_for_retail_fallback(condition_grade)
        visual_multiplier, visual_condition_adjustment = _visual_condition_pricing_multiplier(item_profile)
        estimated_value = retail_reference * factor * condition_multiplier * visual_multiplier
        range_low = estimated_value * 0.85
        range_high = estimated_value * 1.15
        pricing_row_label = "retail_price_estimate_resale_fallback"
        retail_derived = True
    if estimated_value is None:
        return None

    confidence = resale.get("confidence") if isinstance(resale, dict) else None
    if retail_derived:
        retail_confidence = retail.get("confidence") if isinstance(retail, dict) else None
        try:
            confidence = min(float(retail_confidence), 0.35)
        except Exception:
            confidence = 0.35
    try:
        confidence_01 = max(0.0, min(float(confidence), 1.0))
    except Exception:
        confidence_01 = 0.5
    currency = (
        resale.get("currency")
        if isinstance(resale, dict) and isinstance(resale.get("currency"), str)
        else retail.get("currency")
        if isinstance(retail, dict) and isinstance(retail.get("currency"), str)
        else default_currency
    )

    return {
        "estimated_value": round(estimated_value, 2),
        "currency": currency,
        "range_low": round(range_low, 2) if isinstance(range_low, (int, float)) else None,
        "range_high": round(range_high, 2) if isinstance(range_high, (int, float)) else None,
        "confidence": round(confidence_01, 3),
        "basis": (
            "gpt_resale_estimate_primary"
            if pricing_row_label == "resale_price_estimate"
            else "gpt_retail_reference_resale_fallback"
            if pricing_row_label == "retail_price_estimate_resale_fallback"
            else "gpt_resale_breakdown_condition_selected"
        ),
        "comps_summary": {"count": 1, "source_breakdown": {"gpt_item_profile": 1}},
        "resale_market_value": round(estimated_value, 2),
        "retail_reference_value": round(retail_reference, 2) if retail_reference is not None else None,
        "selected_breakdown_label": pricing_row_label if pricing_row_label != "resale_price_estimate" else None,
        "visual_condition_adjustment": visual_condition_adjustment if retail_derived else {"applied": False},
    }


def apply_gemini_grounded_retail_reference(
    item_profile: dict[str, object] | None,
    workflow_debug: object,
    item_profile_debug: dict[str, object],
) -> None:
    if not isinstance(item_profile, dict) or not isinstance(workflow_debug, dict):
        return
    retail = item_profile.get("retail_price_estimate")
    if isinstance(retail, dict) and _coerce_positive_float(retail.get("estimated_price")) is not None:
        return
    grounded_search = workflow_debug.get("grounded_search")
    prices = _extract_retail_prices_from_text(grounded_search)
    if not prices:
        return
    retail_reference = max(prices)
    item_profile["retail_price_estimate"] = {
        "estimated_price": retail_reference,
        "currency": "USD",
        "confidence": 0.35,
        "rationale": "Extracted from Gemini grounded retail evidence because structured retail pricing was missing.",
        "references": [],
    }
    item_profile_debug["retail_reference_extracted"] = {
        "applied": True,
        "estimated_price": round(retail_reference, 2),
        "source": "gemini_grounded_search",
    }


def normalize_category(value: str | None) -> str | None:
    if value is None:
        return None
    norm = value.strip().casefold()
    if norm == "handbags":
        norm = "handbag"
    if norm not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail="category must be clothes|shoes|handbag")
    return norm


def normalize_condition_grade(value: str | None) -> ConditionGrade | None:
    if value is None:
        return None
    norm = value.strip().replace("-", "").replace("_", "").replace(" ", "").casefold()
    if not norm:
        return None
    if norm not in VALID_CONDITION_GRADES:
        raise HTTPException(status_code=400, detail="user_condition must be NewWithTags|New|LikeNew")
    return VALID_CONDITION_GRADES[norm]  # type: ignore[return-value]


def normalize_item_size(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        return None
    if len(cleaned) > 32:
        raise HTTPException(status_code=400, detail="item_size too long (max 32 chars)")
    return cleaned


def build_condition_warnings(user_condition: ConditionGrade | None, model_condition: ConditionGrade) -> list[str]:
    if user_condition is None:
        return []
    if user_condition in {"New", "LikeNew"} and model_condition not in {"New", "LikeNew"}:
        return [
            f"User marked item as {user_condition}, but model assessment suggests {model_condition}. Review wear/damage before listing."
        ]
    return []


def _has_receipt_like_upload(image_inputs: list[ImageInput]) -> bool:
    keywords = ("receipt", "invoice", "authentic", "certificate", "proof", "order")
    for img in image_inputs:
        name = (img.filename or "").casefold()
        hint = (img.role_hint or "").casefold()
        if any(k in name for k in keywords):
            return True
        if any(k in hint for k in keywords):
            return True
    return False


def build_auth_doc_warning(
    item_profile: dict[str, object] | None,
    image_inputs: list[ImageInput],
    *,
    brand_name: str,
) -> str | None:
    if not isinstance(item_profile, dict):
        return None
    expected = item_profile.get("expected_auth_docs")
    usually = ""
    docs_text = ""
    if isinstance(expected, dict):
        usually = str(expected.get("usually_provided") or "").strip().casefold()
        docs = expected.get("typical_documents")
        if isinstance(docs, list):
            cleaned = [d for d in docs if isinstance(d, str) and d.strip()]
            if cleaned:
                docs_text = f" (e.g., {', '.join(cleaned[:3])})"
    if not usually:
        usually = "unknown"

    if usually == "unknown":
        luxury_brands = {
            "louis vuitton", "chanel", "gucci", "prada", "hermes", "dior", "saint laurent",
            "celine", "fendi", "balenciaga", "bottega veneta", "jimmy choo", "valentino",
            "burberry", "loewe", "givenchy", "mcm",
        }
        if brand_name.strip().casefold() in luxury_brands:
            usually = "mixed"

    if usually not in {"yes", "mixed"}:
        return None
    receipt_present = str(item_profile.get("receipt_present") or "").strip().casefold()
    if _has_receipt_like_upload(image_inputs):
        return None
    if receipt_present == "yes":
        return None
    return (
        "For this brand/model, proof of purchase or authenticity documents are usually provided. "
        f"Upload an authenticity receipt image{docs_text} to improve valuation confidence."
    )


def build_valuation_service(settings: Settings, providers: list[str]) -> ValuationService:
    return ValuationService(
        ValuationConfig(
            enabled=settings.valuation_enabled,
            providers=providers or ["stub"],
            currency=settings.valuation_currency,
            min_comps=settings.valuation_min_comps,
            max_comps=settings.valuation_max_comps,
        )
    )


def enrich_analysis_with_firecrawl_agent(
    *,
    analysis_id: str,
    response_payload: dict,
    valuation_request: ValuationRequest,
    settings: Settings,
    db: Database,
) -> None:
    try:
        service = build_valuation_service(settings, ["firecrawl_agent"])
        result = service.evaluate(valuation_request, debug=True)
        serialized = service.serialize(result)
        serialized_debug = serialized.pop("_debug", {}) or {}

        response_payload = dict(response_payload)
        debug_payload = dict(response_payload.get("debug") or {})
        valuation_debug = dict(debug_payload.get("valuation") or {})

        valuation_debug["agent_enrichment"] = {
            "status": "completed" if result.estimated_value is not None else "empty",
            "valuation": serialized,
            "debug": serialized_debug,
        }
        debug_payload["valuation"] = valuation_debug
        response_payload["debug"] = debug_payload
        db.update_analysis_response(analysis_id, response_payload)
    except Exception as exc:
        response_payload = dict(response_payload)
        debug_payload = dict(response_payload.get("debug") or {})
        valuation_debug = dict(debug_payload.get("valuation") or {})
        valuation_debug["agent_enrichment"] = {
            "status": "error",
            "error": str(exc),
        }
        debug_payload["valuation"] = valuation_debug
        response_payload["debug"] = debug_payload
        db.update_analysis_response(analysis_id, response_payload)


@app.get("/v1/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/")
def ui_index():
    return _spa_index_response()


@app.get("/privacy")
def privacy_page():
    return _spa_index_response()


@app.get("/terms")
def terms_page():
    return _spa_index_response()


def _spa_index_response():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="UI not available")
    return FileResponse(index_path)


@app.get("/v1/version", response_model=VersionResponse)
def version(settings: Settings = Depends(get_settings)) -> VersionResponse:
    return VersionResponse(version=settings.version)


@app.get("/v1/me/profile-quiz", response_model=UserProfileQuizResponse)
def get_profile_quiz(
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
):
    row = db.get_user_profile_quiz(principal.subject)
    if row is None:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return UserProfileQuizResponse(
            owner_subject=principal.subject,
            first_name=None,
            last_name=None,
            email=None,
            gender=None,
            birthday=None,
            tops_size=None,
            dresses_size=None,
            bottoms_size=None,
            shoes_size=None,
            category_preferences=[],
            style_descriptors=[],
            jouft_goals=[],
            shipping_full_name=None,
            shipping_address_line1=None,
            shipping_address_line2=None,
            shipping_city=None,
            shipping_state=None,
            shipping_postal_code=None,
            shipping_country=None,
            shipping_email=None,
            shipping_phone=None,
            shipping_addresses=[],
            subscription_plan=None,
            subscription_billing_cycle=None,
            subscription_status=None,
            subscription_renewal_date=None,
            payment_methods=[],
            created_at=now,
            updated_at=now,
        )
    return UserProfileQuizResponse(**row)


@app.put("/v1/me/profile-quiz", response_model=UserProfileQuizResponse)
def put_profile_quiz(
    payload: UserProfileQuizUpdateRequest,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
):
    existing = db.get_user_profile_quiz(principal.subject) or {}
    first_name = str(payload.first_name or "").strip()
    last_name = str(payload.last_name or "").strip()
    email = str(payload.email or "").strip().lower()
    if not first_name:
        raise HTTPException(status_code=400, detail="First name is required.")
    if not last_name:
        raise HTTPException(status_code=400, detail="Last name is required.")
    if not email:
        raise HTTPException(status_code=400, detail="Email address is required.")
    shipping_addresses_payload = [
        a.model_dump() if hasattr(a, "model_dump") else dict(a)
        for a in (payload.shipping_addresses or [])
    ]
    if not shipping_addresses_payload:
        legacy_has_shipping = any(
            bool((v or "").strip()) if isinstance(v, str) else bool(v)
            for v in (
                payload.shipping_full_name,
                payload.shipping_address_line1,
                payload.shipping_address_line2,
                payload.shipping_city,
                payload.shipping_state,
                payload.shipping_postal_code,
                payload.shipping_country,
            )
        )
        if legacy_has_shipping:
            shipping_addresses_payload = [{
                "label": "Primary",
                "full_name": payload.shipping_full_name,
                "address_line1": payload.shipping_address_line1,
                "address_line2": payload.shipping_address_line2,
                "city": payload.shipping_city,
                "state": payload.shipping_state,
                "postal_code": payload.shipping_postal_code,
                "country": payload.shipping_country,
                "is_default": True,
            }]
    primary_shipping = shipping_addresses_payload[0] if shipping_addresses_payload else {}
    saved = db.upsert_user_profile_quiz(
        owner_subject=principal.subject,
        first_name=first_name,
        last_name=last_name,
        email=email,
        gender=payload.gender,
        birthday=payload.birthday,
        tops_size=payload.tops_size,
        dresses_size=payload.dresses_size,
        bottoms_size=payload.bottoms_size,
        shoes_size=payload.shoes_size,
        category_preferences=payload.category_preferences,
        style_descriptors=payload.style_descriptors,
        jouft_goals=payload.jouft_goals,
        shipping_full_name=(
            primary_shipping.get("full_name")
            if isinstance(primary_shipping.get("full_name"), str)
            else payload.shipping_full_name
        ),
        shipping_address_line1=(
            primary_shipping.get("address_line1")
            if isinstance(primary_shipping.get("address_line1"), str)
            else payload.shipping_address_line1
        ),
        shipping_address_line2=(
            primary_shipping.get("address_line2")
            if isinstance(primary_shipping.get("address_line2"), str)
            else payload.shipping_address_line2
        ),
        shipping_city=(
            primary_shipping.get("city")
            if isinstance(primary_shipping.get("city"), str)
            else payload.shipping_city
        ),
        shipping_state=(
            primary_shipping.get("state")
            if isinstance(primary_shipping.get("state"), str)
            else payload.shipping_state
        ),
        shipping_postal_code=(
            primary_shipping.get("postal_code")
            if isinstance(primary_shipping.get("postal_code"), str)
            else payload.shipping_postal_code
        ),
        shipping_country=(
            primary_shipping.get("country")
            if isinstance(primary_shipping.get("country"), str)
            else payload.shipping_country
        ),
        shipping_email=(
            (payload.shipping_email or existing.get("shipping_email") or "").strip() or None
        ),
        shipping_phone=(
            (payload.shipping_phone or existing.get("shipping_phone") or "").strip() or None
        ),
        shipping_addresses=shipping_addresses_payload,
        subscription_plan=payload.subscription_plan,
        subscription_billing_cycle=payload.subscription_billing_cycle,
        subscription_status=payload.subscription_status,
        subscription_renewal_date=payload.subscription_renewal_date,
        payment_methods=payload.payment_methods,
    )
    return UserProfileQuizResponse(**saved)


def _default_client_state(owner_subject: str) -> ClientStateResponse:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return ClientStateResponse(
        owner_subject=owner_subject,
        alert_preferences={},
        liked_listing_ids=[],
        created_at=now,
        updated_at=now,
    )


@app.get("/v1/me/client-state", response_model=ClientStateResponse)
def get_client_state(
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
):
    row = db.get_user_client_state(principal.subject)
    if row is None:
        return _default_client_state(principal.subject)
    return ClientStateResponse(**row)


@app.put("/v1/me/client-state", response_model=ClientStateResponse)
def put_client_state(
    payload: ClientStateUpdateRequest,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
):
    existing = db.get_user_client_state(principal.subject) or {}
    saved = db.upsert_user_client_state(
        owner_subject=principal.subject,
        alert_preferences=(
            payload.alert_preferences
            if payload.alert_preferences is not None
            else dict(existing.get("alert_preferences") or {})
        ),
        liked_listing_ids=(
            payload.liked_listing_ids
            if payload.liked_listing_ids is not None
            else list(existing.get("liked_listing_ids") or [])
        ),
    )
    return ClientStateResponse(**saved)


@app.get("/v1/me/notifications")
def list_notifications(
    limit: int = Query(50, ge=1, le=100),
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
):
    items = db.list_user_notifications(principal.subject, limit=limit)
    return {
        "count": len(items),
        "items": [UserNotificationResponse(**item).model_dump() for item in items],
    }


@app.delete("/v1/me/notifications")
def clear_notifications(
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
):
    deleted = db.delete_user_notifications(principal.subject)
    return {"deleted": deleted}


@app.delete("/v1/me/notifications/{notification_id}")
def delete_notification(
    notification_id: str,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
):
    db.delete_user_notification(principal.subject, notification_id)
    return {"deleted": True}


@app.post("/v1/listings/{listing_id}/like")
def like_listing(
    listing_id: str,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
):
    listing = db.get_listing_by_id(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    owner_subject = str(listing.get("owner_subject") or "").strip()
    if not owner_subject:
        raise HTTPException(status_code=409, detail="Listing owner is unavailable")
    if owner_subject == principal.subject:
        return {"created": False, "reason": "own_listing"}
    title = str(listing.get("title") or "your listing").strip() or "your listing"
    notification = db.create_user_notification(
        notification_id=str(uuid.uuid4()),
        owner_subject=owner_subject,
        actor_subject=principal.subject,
        type="listing-liked",
        title="Listing liked",
        body=f"Someone liked {title}.",
        entity_id=listing_id,
        action_tab="marketplace",
    )
    return {"created": True, "notification": UserNotificationResponse(**notification).model_dump()}


@app.get("/v1/me/payment-methods", response_model=PaymentMethodListResponse)
def list_payment_methods(
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
):
    return PaymentMethodListResponse(items=[PaymentMethodResponse(**m) for m in db.list_payment_methods(principal.subject)])


@app.post("/v1/me/payment-methods", response_model=PaymentMethodResponse)
def create_payment_method(
    payload: PaymentMethodCreateRequest,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
):
    raise HTTPException(
        status_code=400,
        detail="Manual payment method creation is disabled. Use Stripe setup checkout and Stripe sync endpoints.",
    )


@app.post("/v1/me/payment-methods/stripe/attach", response_model=PaymentMethodResponse)
def attach_stripe_payment_method(
    payload: StripeAttachPaymentMethodRequest,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    secret_key = (settings.stripe_secret_key or "").strip()
    if not secret_key:
        raise HTTPException(status_code=400, detail="Stripe not configured on server")
    stripe_pm_id = (payload.payment_method_id or "").strip()
    if not stripe_pm_id:
        raise HTTPException(status_code=400, detail="payment_method_id is required")

    customer_id = db.get_stripe_customer_id(principal.subject)
    if not customer_id:
        raise HTTPException(status_code=400, detail="Stripe customer not initialized. Create setup intent first.")
    try:
        with httpx.Client(timeout=10.0) as client:
            attach_resp = client.post(
                f"https://api.stripe.com/v1/payment_methods/{stripe_pm_id}/attach",
                data={"customer": customer_id},
                auth=(secret_key, ""),
            )
            if attach_resp.status_code >= 400 and "already attached" not in (attach_resp.text or "").lower():
                raise HTTPException(status_code=502, detail="Stripe payment method attach failed")
            pm_resp = client.get(
                f"https://api.stripe.com/v1/payment_methods/{stripe_pm_id}",
                auth=(secret_key, ""),
            )
            if pm_resp.status_code >= 400:
                raise HTTPException(status_code=502, detail="Stripe payment method lookup failed")
            pm = pm_resp.json()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Stripe unavailable")

    pm_type = str(pm.get("type") or "card")
    card = pm.get("card") if isinstance(pm.get("card"), dict) else {}
    wallet = card.get("wallet") if isinstance(card, dict) and isinstance(card.get("wallet"), dict) else {}
    method_type = "apple_pay" if (wallet.get("type") == "apple_pay") else "card"
    brand = str(card.get("brand") or "").strip() or None
    last4 = str(card.get("last4") or "").strip() or None
    exp_month = int(card.get("exp_month")) if isinstance(card.get("exp_month"), int) else None
    exp_year = int(card.get("exp_year")) if isinstance(card.get("exp_year"), int) else None
    label = ("Apple Pay" if method_type == "apple_pay" else (brand.title() if brand else "Card"))
    if last4:
        label = f"{label} •••• {last4}"
    billing = pm.get("billing_details") if isinstance(pm.get("billing_details"), dict) else {}
    email = str(billing.get("email") or "").strip() or None

    method = db.create_payment_method(
        payment_method_id=f"pm-local-{uuid.uuid4()}",
        owner_subject=principal.subject,
        provider="stripe",
        method_type=method_type if pm_type == "card" else "card",
        label=label,
        last4=last4,
        brand=brand,
        exp_month=exp_month,
        exp_year=exp_year,
        email=email,
        provider_token=stripe_pm_id,
        is_default=payload.is_default,
    )
    return PaymentMethodResponse(**method)


@app.delete("/v1/me/payment-methods/{payment_method_id}")
def delete_payment_method(
    payment_method_id: str,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    existing = db.get_payment_method(principal.subject, payment_method_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Payment method not found")

    provider = str(existing.get("provider") or "").strip().lower()
    provider_token = str(existing.get("provider_token") or "").strip()
    secret_key = (settings.stripe_secret_key or "").strip()
    if provider == "stripe" and provider_token and secret_key:
        try:
            with httpx.Client(timeout=10.0) as client:
                detach_resp = client.post(
                    f"https://api.stripe.com/v1/payment_methods/{provider_token}/detach",
                    auth=(secret_key, ""),
                )
            if detach_resp.status_code >= 400:
                payload = detach_resp.json() if detach_resp.content else {}
                code = (
                    payload.get("error", {}).get("code")
                    if isinstance(payload, dict) and isinstance(payload.get("error"), dict)
                    else None
                )
                # If already detached/missing in Stripe, continue local delete.
                if code not in {"resource_missing", "payment_method_unexpected_state"}:
                    raise HTTPException(status_code=502, detail="Failed to detach payment method in Stripe")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=502, detail="Stripe unavailable while deleting payment method")

    deleted = db.delete_payment_method(principal.subject, payment_method_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Payment method not found")
    return {"status": "deleted"}


@app.post("/v1/me/payment-methods/{payment_method_id}/default", response_model=PaymentMethodResponse)
def set_default_payment_method(
    payment_method_id: str,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
):
    method = db.set_default_payment_method(principal.subject, payment_method_id)
    if method is None:
        raise HTTPException(status_code=404, detail="Payment method not found")
    return PaymentMethodResponse(**method)


def _stripe_error_detail(response: httpx.Response, fallback: str) -> str:
    try:
        payload = response.json()
        message = str(payload.get("error", {}).get("message") or "").strip()
        if message:
            return f"{fallback}: {message}"
    except Exception:
        pass
    return fallback


def _date_from_stripe_epoch(value: object) -> str | None:
    if not isinstance(value, int) or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc).date().isoformat()
    except Exception:
        return None


@app.post("/v1/me/subscription/activate", response_model=SubscriptionActivateResponse)
def activate_subscription(
    payload: SubscriptionActivateRequest,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    plan_key = str(payload.plan or "").strip()
    cycle = str(payload.billing_cycle or "monthly").strip()
    plan = SUBSCRIPTION_PLANS.get(plan_key)
    if not plan:
        raise HTTPException(status_code=400, detail="Unknown subscription plan")
    if cycle not in {"monthly", "annual"}:
        raise HTTPException(status_code=400, detail="Unknown billing cycle")

    existing_billing = db.get_billing_profile(principal.subject) or {}
    existing_subscription_id = str(existing_billing.get("stripe_subscription_id") or "").strip()

    if plan_key == "free":
        status = "free"
        renewal_date = None
        message = "Free plan active."
        persisted_subscription_id = None
        secret_key = (settings.stripe_secret_key or "").strip()
        if secret_key and existing_subscription_id:
            try:
                with httpx.Client(timeout=10.0) as client:
                    cancel_resp = client.post(
                        f"https://api.stripe.com/v1/subscriptions/{existing_subscription_id}",
                        data={"cancel_at_period_end": "true"},
                        auth=(secret_key, ""),
                    )
                if cancel_resp.status_code < 400:
                    cancel_data = cancel_resp.json()
                    status = "canceling"
                    renewal_date = _date_from_stripe_epoch(cancel_data.get("current_period_end"))
                    persisted_subscription_id = existing_subscription_id
                    message = "Paid subscription will end at the current billing period. Free plan selected."
            except Exception:
                status = "free"
                message = "Free plan active. Existing Stripe subscription could not be canceled automatically."
        db.set_billing_subscription(
            principal.subject,
            stripe_subscription_id=persisted_subscription_id,
            subscription_plan=plan_key,
            subscription_billing_cycle=cycle,
            subscription_status=status,
            subscription_renewal_date=renewal_date,
        )
        db.update_profile_subscription(
            principal.subject,
            subscription_plan=plan_key,
            subscription_billing_cycle=cycle,
            subscription_status=status,
            subscription_renewal_date=renewal_date,
        )
        return SubscriptionActivateResponse(
            owner_subject=principal.subject,
            plan=plan_key,
            billing_cycle=cycle,
            status=status,
            renewal_date=renewal_date,
            stripe_subscription_id=persisted_subscription_id,
            message=message,
        )

    secret_key = (settings.stripe_secret_key or "").strip()
    if not secret_key:
        raise HTTPException(status_code=400, detail="Stripe not configured on server")

    methods = db.list_payment_methods(principal.subject)
    selected_method_id = str(payload.payment_method_id or "").strip()
    selected_method = None
    if selected_method_id:
        selected_method = db.get_payment_method(principal.subject, selected_method_id)
    if selected_method is None:
        default_id = next((m.get("payment_method_id") for m in methods if m.get("is_default")), None)
        if default_id:
            selected_method = db.get_payment_method(principal.subject, str(default_id))
    if selected_method is None and methods:
        selected_method = db.get_payment_method(principal.subject, str(methods[0].get("payment_method_id") or ""))
    if selected_method is None:
        raise HTTPException(status_code=402, detail="Add a payment method before activating a paid plan")
    provider = str(selected_method.get("provider") or "").strip().lower()
    provider_token = str(selected_method.get("provider_token") or "").strip()
    if provider != "stripe" or not provider_token:
        raise HTTPException(status_code=400, detail="A Stripe payment method is required for paid plans")

    customer_id = db.get_stripe_customer_id(principal.subject)
    if not customer_id:
        raise HTTPException(status_code=400, detail="Stripe customer not initialized. Add a payment method first.")

    interval = "year" if cycle == "annual" else "month"
    amount_cents = int(plan["annual_cents"] if cycle == "annual" else plan["monthly_cents"])
    subscription_data: dict = {}
    try:
        with httpx.Client(timeout=15.0) as client:
            customer_resp = client.post(
                f"https://api.stripe.com/v1/customers/{customer_id}",
                data={"invoice_settings[default_payment_method]": provider_token},
                auth=(secret_key, ""),
            )
            if customer_resp.status_code >= 400:
                raise HTTPException(status_code=502, detail=_stripe_error_detail(customer_resp, "Stripe customer update failed"))

            if existing_subscription_id:
                existing_resp = client.get(
                    f"https://api.stripe.com/v1/subscriptions/{existing_subscription_id}",
                    auth=(secret_key, ""),
                )
                if existing_resp.status_code < 400:
                    existing_data = existing_resp.json()
                    existing_status = str(existing_data.get("status") or "").lower()
                    metadata = existing_data.get("metadata") if isinstance(existing_data.get("metadata"), dict) else {}
                    if (
                        existing_status in {"active", "trialing", "past_due", "incomplete"}
                        and str(metadata.get("plan") or "") == plan_key
                        and str(metadata.get("billing_cycle") or "") == cycle
                    ):
                        if bool(existing_data.get("cancel_at_period_end")):
                            resume_resp = client.post(
                                f"https://api.stripe.com/v1/subscriptions/{existing_subscription_id}",
                                data={"cancel_at_period_end": "false"},
                                auth=(secret_key, ""),
                            )
                            if resume_resp.status_code >= 400:
                                raise HTTPException(status_code=502, detail=_stripe_error_detail(resume_resp, "Stripe subscription update failed"))
                            existing_data = resume_resp.json()
                            existing_status = str(existing_data.get("status") or existing_status).lower()
                        renewal_date = _date_from_stripe_epoch(existing_data.get("current_period_end"))
                        db.set_billing_subscription(
                            principal.subject,
                            stripe_subscription_id=existing_subscription_id,
                            subscription_plan=plan_key,
                            subscription_billing_cycle=cycle,
                            subscription_status=existing_status,
                            subscription_renewal_date=renewal_date,
                        )
                        db.update_profile_subscription(
                            principal.subject,
                            subscription_plan=plan_key,
                            subscription_billing_cycle=cycle,
                            subscription_status=existing_status,
                            subscription_renewal_date=renewal_date,
                        )
                        return SubscriptionActivateResponse(
                            owner_subject=principal.subject,
                            plan=plan_key,
                            billing_cycle=cycle,
                            status=existing_status,
                            renewal_date=renewal_date,
                            stripe_subscription_id=existing_subscription_id,
                            message="Subscription already active.",
                        )
                    if existing_status not in {"canceled", "incomplete_expired"}:
                        cancel_resp = client.request(
                            "DELETE",
                            f"https://api.stripe.com/v1/subscriptions/{existing_subscription_id}",
                            data={"invoice_now": "false", "prorate": "false"},
                            auth=(secret_key, ""),
                        )
                        if cancel_resp.status_code >= 400:
                            raise HTTPException(status_code=502, detail=_stripe_error_detail(cancel_resp, "Stripe subscription replacement failed"))

            product_resp = client.post(
                "https://api.stripe.com/v1/products",
                data={
                    "name": str(plan["label"]),
                    "metadata[plan]": plan_key,
                },
                auth=(secret_key, ""),
            )
            if product_resp.status_code >= 400:
                raise HTTPException(status_code=502, detail=_stripe_error_detail(product_resp, "Stripe product creation failed"))
            product_id = str(product_resp.json().get("id") or "").strip()
            if not product_id:
                raise HTTPException(status_code=502, detail="Stripe product creation failed")

            subscription_resp = client.post(
                "https://api.stripe.com/v1/subscriptions",
                data={
                    "customer": customer_id,
                    "default_payment_method": provider_token,
                    "items[0][price_data][currency]": "usd",
                    "items[0][price_data][unit_amount]": str(amount_cents),
                    "items[0][price_data][recurring][interval]": interval,
                    "items[0][price_data][product]": product_id,
                    "metadata[owner_subject]": principal.subject,
                    "metadata[plan]": plan_key,
                    "metadata[billing_cycle]": cycle,
                    "payment_behavior": "error_if_incomplete",
                    "expand[]": "latest_invoice.payment_intent",
                },
                auth=(secret_key, ""),
            )
            if subscription_resp.status_code >= 400:
                raise HTTPException(status_code=502, detail=_stripe_error_detail(subscription_resp, "Stripe subscription creation failed"))
            subscription_data = subscription_resp.json()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Stripe unavailable")

    subscription_id = str(subscription_data.get("id") or "").strip() or None
    status = str(subscription_data.get("status") or "active").strip() or "active"
    renewal_date = _date_from_stripe_epoch(subscription_data.get("current_period_end"))
    db.set_billing_subscription(
        principal.subject,
        stripe_subscription_id=subscription_id,
        subscription_plan=plan_key,
        subscription_billing_cycle=cycle,
        subscription_status=status,
        subscription_renewal_date=renewal_date,
    )
    db.update_profile_subscription(
        principal.subject,
        subscription_plan=plan_key,
        subscription_billing_cycle=cycle,
        subscription_status=status,
        subscription_renewal_date=renewal_date,
    )
    return SubscriptionActivateResponse(
        owner_subject=principal.subject,
        plan=plan_key,
        billing_cycle=cycle,
        status=status,
        renewal_date=renewal_date,
        stripe_subscription_id=subscription_id,
        message="Subscription active.",
    )


@app.post("/v1/me/payment-methods/stripe/setup-intent", response_model=StripeSetupIntentResponse)
def create_stripe_setup_intent(
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    secret_key = (settings.stripe_secret_key or "").strip()
    if not secret_key:
        return StripeSetupIntentResponse(
            client_secret=None,
            customer_id=None,
            publishable_key=settings.stripe_publishable_key,
            status="disabled",
            message="Stripe not configured on server",
        )
    email = (
        str(principal.claims.get("email") or "").strip()
        if isinstance(principal.claims, dict)
        else ""
    ) or None
    customer_id = db.get_stripe_customer_id(principal.subject)
    try:
        with httpx.Client(timeout=10.0) as client:
            if not customer_id:
                customer_resp = client.post(
                    "https://api.stripe.com/v1/customers",
                    data={"metadata[owner_subject]": principal.subject, **({"email": email} if email else {})},
                    auth=(secret_key, ""),
                )
                if customer_resp.status_code >= 400:
                    raise HTTPException(status_code=502, detail="Stripe customer creation failed")
                customer_id = str(customer_resp.json().get("id") or "")
                if customer_id:
                    db.set_stripe_customer_id(principal.subject, customer_id)
            si_resp = client.post(
                "https://api.stripe.com/v1/setup_intents",
                data={"customer": customer_id, "usage": "off_session", "automatic_payment_methods[enabled]": "true"},
                auth=(secret_key, ""),
            )
            if si_resp.status_code >= 400:
                raise HTTPException(status_code=502, detail="Stripe setup intent creation failed")
            client_secret = str(si_resp.json().get("client_secret") or "")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Stripe unavailable")
    return StripeSetupIntentResponse(
        client_secret=client_secret or None,
        customer_id=customer_id or None,
        publishable_key=settings.stripe_publishable_key,
        status="ok",
        message=None,
    )


@app.post("/v1/me/payment-methods/stripe/setup-checkout-session", response_model=StripeSetupCheckoutResponse)
def create_stripe_setup_checkout_session(
    payload: StripeSetupCheckoutRequest,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    secret_key = (settings.stripe_secret_key or "").strip()
    if not secret_key:
        return StripeSetupCheckoutResponse(status="disabled", message="Stripe not configured on server")
    customer_id = db.get_stripe_customer_id(principal.subject)
    email = (
        str(principal.claims.get("email") or "").strip()
        if isinstance(principal.claims, dict)
        else ""
    ) or None
    try:
        with httpx.Client(timeout=10.0) as client:
            if not customer_id:
                customer_resp = client.post(
                    "https://api.stripe.com/v1/customers",
                    data={"metadata[owner_subject]": principal.subject, **({"email": email} if email else {})},
                    auth=(secret_key, ""),
                )
                if customer_resp.status_code >= 400:
                    raise HTTPException(status_code=502, detail="Stripe customer creation failed")
                customer_id = str(customer_resp.json().get("id") or "")
                if customer_id:
                    db.set_stripe_customer_id(principal.subject, customer_id)
            session_resp = client.post(
                "https://api.stripe.com/v1/checkout/sessions",
                data={
                    "mode": "setup",
                    "customer": customer_id or "",
                    "payment_method_types[]": "card",
                    "success_url": payload.success_url,
                    "cancel_url": payload.cancel_url,
                },
                auth=(secret_key, ""),
            )
            if session_resp.status_code >= 400:
                stripe_detail = "Stripe checkout session creation failed"
                try:
                    stripe_message = str(session_resp.json().get("error", {}).get("message") or "").strip()
                    if stripe_message:
                        stripe_detail = f"{stripe_detail}: {stripe_message}"
                except Exception:
                    pass
                raise HTTPException(status_code=502, detail=stripe_detail)
            session_data = session_resp.json()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Stripe unavailable")
    return StripeSetupCheckoutResponse(
        checkout_url=str(session_data.get("url") or "") or None,
        session_id=str(session_data.get("id") or "") or None,
        status="ok",
    )


@app.post("/v1/me/payment-methods/stripe/sync", response_model=PaymentMethodListResponse)
def sync_stripe_payment_methods(
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    secret_key = (settings.stripe_secret_key or "").strip()
    customer_id = db.get_stripe_customer_id(principal.subject)
    if not secret_key or not customer_id:
        return PaymentMethodListResponse(items=[PaymentMethodResponse(**m) for m in db.list_payment_methods(principal.subject)])
    try:
        with httpx.Client(timeout=10.0) as client:
            items: list[dict] = []
            for stripe_type in ("card", "link"):
                list_resp = client.get(
                    "https://api.stripe.com/v1/payment_methods",
                    params={"customer": customer_id, "type": stripe_type},
                    auth=(secret_key, ""),
                )
                if list_resp.status_code >= 400:
                    raise HTTPException(status_code=502, detail="Stripe payment methods list failed")
                payload_items = list_resp.json().get("data") or []
                if isinstance(payload_items, list):
                    items.extend(payload_items)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Stripe unavailable")

    for pm in items:
        pm_id = str(pm.get("id") or "").strip()
        if not pm_id:
            continue
        stripe_pm_type = str(pm.get("type") or "").strip()
        card = pm.get("card") if isinstance(pm.get("card"), dict) else {}
        wallet = card.get("wallet") if isinstance(card, dict) and isinstance(card.get("wallet"), dict) else {}
        if stripe_pm_type == "link":
            method_type = "link"
        else:
            method_type = "apple_pay" if wallet.get("type") == "apple_pay" else "card"
        brand = str(card.get("brand") or "").strip() or None
        last4 = str(card.get("last4") or "").strip() or None
        exp_month = int(card.get("exp_month")) if isinstance(card.get("exp_month"), int) else None
        exp_year = int(card.get("exp_year")) if isinstance(card.get("exp_year"), int) else None
        label = ("Link" if method_type == "link" else ("Apple Pay" if method_type == "apple_pay" else (brand.title() if brand else "Card")))
        if last4 and method_type != "link":
            label = f"{label} •••• {last4}"
        billing = pm.get("billing_details") if isinstance(pm.get("billing_details"), dict) else {}
        email = str(billing.get("email") or "").strip() or None
        if method_type == "link" and email:
            label = f"Link ({email})"
        db.delete_payment_method_by_provider_token(principal.subject, "stripe", pm_id)
        db.create_payment_method(
            payment_method_id=f"pm-stripe-{pm_id}",
            owner_subject=principal.subject,
            provider="stripe",
            method_type=method_type,
            label=label,
            last4=last4,
            brand=brand,
            exp_month=exp_month,
            exp_year=exp_year,
            email=email,
            provider_token=pm_id,
            is_default=False,
        )
    methods = db.list_payment_methods(principal.subject)
    if methods and not any(m.get("is_default") for m in methods):
        db.set_default_payment_method(principal.subject, methods[0]["payment_method_id"])
        methods = db.list_payment_methods(principal.subject)
    return PaymentMethodListResponse(items=[PaymentMethodResponse(**m) for m in methods])


def _shippo_address_suggest(
    *,
    q: str,
    city: str | None,
    state: str | None,
    postal_code: str | None,
    settings: Settings,
) -> dict:
    key = (settings.shippo_api_key or "").strip()
    if not key:
        return {"suggestions": []}
    street = (q or "").strip()
    requested_city = (city or "").strip()
    requested_postal = (postal_code or "").strip()
    if len(street) < 3:
        return {"suggestions": []}
    normalized_state = (state or "").strip().upper()
    payload: dict[str, object] = {
        "street1": street,
        "country": "US",
        "validate": True,
    }
    if requested_city:
        payload["city"] = requested_city
    if len(normalized_state) == 2:
        payload["state"] = normalized_state
    if requested_postal:
        payload["zip"] = requested_postal[:10]
    headers = {
        "Authorization": f"ShippoToken {key}",
        "Content-Type": "application/json",
    }
    base = settings.shippo_api_base_url.rstrip("/")
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(f"{base}/addresses/", json=payload, headers=headers)
        if resp.status_code >= 400:
            return {"suggestions": []}
        body = resp.json() if resp.content else {}
    except Exception:
        return {"suggestions": []}
    if not isinstance(body, dict):
        return {"suggestions": []}
    street_line = str(body.get("street1") or body.get("street_no") or "").strip()
    city_name = str(body.get("city") or requested_city).strip()
    state_code = str(body.get("state") or normalized_state).strip().upper()
    postal = str(body.get("zip") or requested_postal).strip()
    if not street_line:
        return {"suggestions": []}
    formatted = ", ".join([x for x in [street_line, city_name, state_code, postal] if x])
    return {
        "suggestions": [{
            "street_address": street_line,
            "city": city_name,
            "state": state_code,
            "postal_code": postal,
            "formatted": formatted,
        }]
    }


def _usps_address_suggest(
    *,
    q: str,
    city: str | None,
    state: str | None,
    postal_code: str | None,
    settings: Settings,
) -> dict:
    token = (settings.usps_bearer_token or "").strip()
    if not token:
        return {"suggestions": []}
    street = (q or "").strip()
    if len(street) < 3:
        return {"suggestions": []}
    normalized_state = (state or "").strip().upper()
    params: dict[str, str] = {"streetAddress": street}
    if len(normalized_state) == 2:
        params["state"] = normalized_state
    if city and city.strip():
        params["city"] = city.strip()
    elif postal_code and postal_code.strip():
        params["ZIPCode"] = postal_code.strip()[:5]
    try:
        with httpx.Client(timeout=settings.usps_timeout_s) as client:
            resp = client.get(
                settings.usps_addresses_api_url,
                params=params,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
            )
        if resp.status_code >= 400:
            return {"suggestions": []}
        body = resp.json() if resp.content else {}
    except Exception:
        return {"suggestions": []}
    address = body.get("address") if isinstance(body, dict) else None
    if not isinstance(address, dict):
        return {"suggestions": []}
    street_line = str(address.get("streetAddressAbbreviation") or address.get("streetAddress") or "").strip()
    city_name = str(address.get("cityAbbreviation") or address.get("city") or city or "").strip()
    state_code = str(address.get("state") or normalized_state).strip().upper()
    zip_code = str(address.get("ZIPCode") or "").strip()
    plus4 = str(address.get("ZIPPlus4") or "").strip()
    postal = zip_code if not plus4 else f"{zip_code}-{plus4}"
    if not street_line:
        return {"suggestions": []}
    formatted = ", ".join([x for x in [street_line, city_name, state_code, postal] if x])
    return {
        "suggestions": [{
            "street_address": street_line,
            "city": city_name,
            "state": state_code,
            "postal_code": postal,
            "formatted": formatted,
        }]
    }


def _google_places_address_suggest(
    *,
    q: str,
    city: str | None,
    state: str | None,
    postal_code: str | None,
    settings: Settings,
) -> dict:
    key = (settings.google_places_api_key or "").strip()
    query = " ".join(
        part
        for part in [
            (q or "").strip(),
            (city or "").strip(),
            (state or "").strip().upper(),
            (postal_code or "").strip(),
        ]
        if part
    )
    if not key or len((q or "").strip()) < 3:
        return {"suggestions": []}
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": "suggestions.placePrediction.placeId,suggestions.placePrediction.text",
    }
    payload = {
        "input": query,
        "includedPrimaryTypes": ["street_address", "premise"],
        "includedRegionCodes": ["us"],
        "languageCode": "en-US",
    }
    try:
        with httpx.Client(timeout=settings.google_places_timeout_s) as client:
            resp = client.post(settings.google_places_autocomplete_url, json=payload, headers=headers)
        if resp.status_code >= 400:
            return {"suggestions": []}
        body = resp.json() if resp.content else {}
    except Exception:
        return {"suggestions": []}
    raw_suggestions = body.get("suggestions") if isinstance(body, dict) else None
    if not isinstance(raw_suggestions, list):
        return {"suggestions": []}

    suggestions: list[dict[str, str | None]] = []
    with httpx.Client(timeout=settings.google_places_timeout_s) as client:
        for raw in raw_suggestions[:5]:
            prediction = raw.get("placePrediction") if isinstance(raw, dict) else None
            if not isinstance(prediction, dict):
                continue
            place_id = str(prediction.get("placeId") or "").strip()
            text_obj = prediction.get("text") if isinstance(prediction.get("text"), dict) else {}
            formatted = str(text_obj.get("text") or "").strip()
            if not place_id:
                continue
            detail_headers = {
                "X-Goog-Api-Key": key,
                "X-Goog-FieldMask": "formattedAddress,addressComponents",
            }
            try:
                detail_resp = client.get(
                    settings.google_places_details_url.format(place_id=place_id),
                    headers=detail_headers,
                )
                if detail_resp.status_code >= 400:
                    continue
                detail = detail_resp.json() if detail_resp.content else {}
            except Exception:
                continue
            components = detail.get("addressComponents") if isinstance(detail, dict) else None
            if not isinstance(components, list):
                continue
            by_type: dict[str, dict] = {}
            for component in components:
                if not isinstance(component, dict):
                    continue
                for ctype in component.get("types") or []:
                    by_type[str(ctype)] = component

            def comp_long(name: str) -> str:
                component = by_type.get(name) or {}
                return str(component.get("longText") or component.get("long_name") or "").strip()

            def comp_short(name: str) -> str:
                component = by_type.get(name) or {}
                return str(component.get("shortText") or component.get("short_name") or comp_long(name)).strip()

            street_number = comp_long("street_number")
            route = comp_long("route")
            street_line = " ".join(part for part in [street_number, route] if part).strip()
            city_name = (
                comp_long("locality")
                or comp_long("postal_town")
                or comp_long("sublocality")
                or comp_long("administrative_area_level_3")
            )
            state_code = comp_short("administrative_area_level_1").upper()
            zip_code = comp_long("postal_code")
            zip_suffix = comp_long("postal_code_suffix")
            postal = zip_code if not zip_suffix else f"{zip_code}-{zip_suffix}"
            country = comp_short("country").upper() or "US"
            formatted_address = str(detail.get("formattedAddress") or formatted).strip()
            if not street_line:
                continue
            suggestions.append(
                {
                    "street_address": street_line,
                    "city": city_name,
                    "state": state_code,
                    "postal_code": postal,
                    "country": country,
                    "formatted": formatted_address or ", ".join([x for x in [street_line, city_name, state_code, postal] if x]),
                    "place_id": place_id,
                    "provider": "google_places",
                }
            )
    return {"suggestions": suggestions}


@app.get("/v1/shippo/address-suggest")
def shippo_address_suggest(
    q: str = Query(default="", min_length=0, max_length=120),
    city: str | None = Query(default=None, max_length=80),
    state: str | None = Query(default=None, max_length=2),
    postal_code: str | None = Query(default=None, max_length=10),
    settings: Settings = Depends(get_settings),
):
    return _shippo_address_suggest(
        q=q,
        city=city,
        state=state,
        postal_code=postal_code,
        settings=settings,
    )


@app.get("/v1/google/places/address-suggest")
def google_places_address_suggest(
    q: str = Query(default="", min_length=0, max_length=120),
    city: str | None = Query(default=None, max_length=80),
    state: str | None = Query(default=None, max_length=2),
    postal_code: str | None = Query(default=None, max_length=10),
    settings: Settings = Depends(get_settings),
):
    return _google_places_address_suggest(
        q=q,
        city=city,
        state=state,
        postal_code=postal_code,
        settings=settings,
    )


@app.get("/v1/usps/address-suggest")
def usps_address_suggest_alias(
    q: str = Query(default="", min_length=0, max_length=120),
    city: str | None = Query(default=None, max_length=80),
    state: str | None = Query(default=None, max_length=2),
    postal_code: str | None = Query(default=None, max_length=10),
    settings: Settings = Depends(get_settings),
):
    return _usps_address_suggest(
        q=q,
        city=city,
        state=state,
        postal_code=postal_code,
        settings=settings,
    )


@app.get("/v1/images/{image_id}")
def get_uploaded_image(
    image_id: str,
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    storage_uri = db.get_image_storage_uri(image_id)
    if not storage_uri:
        raise HTTPException(status_code=404, detail="image not found")

    if storage_uri.startswith("http://") or storage_uri.startswith("https://"):
        return RedirectResponse(storage_uri, status_code=307)

    streamed = _stream_s3_uri(storage_uri, settings)
    if streamed:
        return streamed

    path = Path(storage_uri)
    candidate_paths = [path]
    if not path.is_absolute():
        # Support legacy relative storage paths regardless of process cwd.
        base = Path(settings.local_storage_dir).resolve().parent
        candidate_paths.append((base / path).resolve())
        candidate_paths.append((Path(settings.local_storage_dir).resolve() / path).resolve())
    for candidate in candidate_paths:
        if candidate.exists():
            return FileResponse(candidate)
    raise HTTPException(status_code=404, detail="image not found")


@app.get("/v1/share/listings/{listing_id}", response_class=HTMLResponse)
def public_listing_share_page(
    listing_id: str,
    request: Request,
    db: Database = Depends(get_db),
):
    listing = db.get_listing_by_id(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="listing not found")

    title = str(listing.get("title") or "Jouft Listing").strip() or "Jouft Listing"
    brand = str(listing.get("brand") or "Unknown brand").strip() or "Unknown brand"
    condition = str(listing.get("condition") or "Unknown condition").strip() or "Unknown condition"
    value = listing.get("estimated_value")
    description = str(listing.get("description") or listing.get("wants") or "").strip()
    if not description:
        price_text = f"${float(value):.0f}" if isinstance(value, (int, float)) else "N/A"
        description = f"{brand} • {condition} • Est. {price_text}"

    gallery = listing.get("images") if isinstance(listing.get("images"), list) else []
    primary_image = None
    if gallery:
        primary_image = gallery[0]
    if not primary_image:
        primary_image = listing.get("image")
    image_url = str(primary_image).strip() if isinstance(primary_image, str) else ""
    if image_url.startswith("/"):
        image_url = str(request.base_url).rstrip("/") + image_url
    if not image_url.startswith("http://") and not image_url.startswith("https://"):
        image_url = ""

    page_url = str(request.url)
    escaped_title = html_escape(title)
    escaped_description = html_escape(description)
    escaped_brand = html_escape(brand)
    escaped_condition = html_escape(condition)
    escaped_image = html_escape(image_url) if image_url else ""
    escaped_page_url = html_escape(page_url)

    image_meta = f"""
    <meta property="og:image" content="{escaped_image}" />
    <meta property="twitter:image" content="{escaped_image}" />
    """ if escaped_image else ""

    image_html = ""
    if escaped_image:
        image_html = f'<img src="{escaped_image}" alt="{escaped_title}" style="max-width: 100%; height: auto; border: 1px solid #ddd;" />'

    html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{escaped_title} | Jouft</title>
    <meta name="description" content="{escaped_description}" />
    <meta property="og:type" content="website" />
    <meta property="og:site_name" content="Jouft" />
    <meta property="og:title" content="{escaped_title}" />
    <meta property="og:description" content="{escaped_description}" />
    <meta property="og:url" content="{escaped_page_url}" />
    {image_meta}
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{escaped_title}" />
    <meta name="twitter:description" content="{escaped_description}" />
  </head>
  <body style="font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif; margin: 24px; color:#1a1a1a;">
    <h1 style="margin-bottom: 8px;">{escaped_title}</h1>
    <p style="margin: 0 0 8px 0; color:#555;">{escaped_brand} • {escaped_condition}</p>
    <p style="max-width: 720px;">{escaped_description}</p>
    {image_html}
  </body>
</html>"""
    return HTMLResponse(content=html, status_code=200)


@app.get("/v1/admin/analyses")
def admin_recent_analyses(
    limit: int = 25,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
):
    safe_limit = max(1, min(limit, 100))
    records = db.list_recent_analyses(limit=safe_limit)
    return {
        "count": len(records),
        "items": records,
        "actor": {"auth_type": principal.auth_type, "subject": principal.subject},
    }


@app.post("/v1/listings", response_model=ListingResponse)
def create_listing(
    payload: ListingCreateRequest,
    background_tasks: BackgroundTasks,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
    valuation_service: ValuationService = Depends(get_valuation_service),
    gpt_item_profiler=Depends(get_gpt_item_profiler),
):
    normalized_image, normalized_images = _normalize_listing_media_for_storage(
        db=db,
        image=payload.image,
        images=_listing_storage_images(payload.images, payload.analysis, payload.listed_images),
        source_item_id=payload.source_item_id,
    )
    listing_id = str(uuid.uuid4())
    owner_name = None
    if principal.auth_type == "clerk":
        owner_name = (
            principal.claims.get("name")
            or " ".join(
                p for p in [
                    principal.claims.get("first_name") or principal.claims.get("given_name"),
                    principal.claims.get("last_name") or principal.claims.get("family_name"),
                ] if isinstance(p, str) and p.strip()
            )
            or principal.claims.get("username")
            or principal.claims.get("email")
        )
        if isinstance(owner_name, str):
            owner_name = owner_name.strip()
    if not owner_name or owner_name == principal.subject or owner_name.lower().startswith("user_"):
        profile = db.get_user_profile_quiz(principal.subject) or {}
        profile_name = " ".join(
            p for p in [
                profile.get("first_name"),
                profile.get("last_name"),
            ] if isinstance(p, str) and p.strip()
        ).strip()
        owner_name = profile_name or (profile.get("shipping_full_name") if isinstance(profile.get("shipping_full_name"), str) else "")
        if isinstance(owner_name, str):
            owner_name = owner_name.strip()
    if not owner_name:
        owner_name = "Member"
    created_at = db.insert_listing(
        listing_id=listing_id,
        owner_subject=principal.subject,
        owner_name=owner_name,
        title=payload.title,
        mode="trade",
        category=payload.category,
        brand=payload.brand,
        condition=payload.condition,
        size=payload.size,
        estimated_value=payload.estimated_value,
        city=payload.city,
        image=normalized_image,
        images=normalized_images,
        description=payload.description,
        wants=payload.wants,
        tags=payload.tags,
        source_item_id=payload.source_item_id,
        analysis=payload.analysis,
        status=payload.status,
    )
    response_payload = payload.model_dump()
    response_payload["image"] = normalized_image
    response_payload["images"] = _display_image_urls_from_storage_images(normalized_images)
    response_payload["listed_images"] = [
        entry if isinstance(entry, dict) else {"p_img": entry, "d_img": entry, "is_hero": entry == normalized_image}
        for entry in normalized_images
    ]
    if str(payload.status or "").lower() == "analyzing":
        background_tasks.add_task(
            _run_listing_analysis_for_existing_listing_job,
            listing_id=listing_id,
            owner_subject=principal.subject,
            category=payload.category,
            item_size=payload.size,
            user_condition=payload.condition,
            item_description=payload.description,
            debug=True,
            settings=settings,
            valuation_service=valuation_service,
            gpt_item_profiler=gpt_item_profiler,
            stage_images_after_analysis=True,
        )
        log_json("listing_analysis_auto_queued", listing_id=listing_id, actor=principal.subject)
    return ListingResponse(
        listing_id=listing_id,
        owner_subject=principal.subject,
        owner_name=owner_name,
        created_at=created_at,
        **response_payload,
    )


@app.get("/v1/listings")
def list_recent_listings(
    limit: int = 50,
    offset: int = 0,
    mine: bool = False,
    include_matches: bool = False,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    def _to_http_image_url(value: object) -> str | None:
        normalized_public_url = _normalize_public_image_url(value)
        if normalized_public_url:
            return normalized_public_url
        s = value.strip() if isinstance(value, str) else ""
        if s.startswith("s3://"):
            try:
                signed = _presign_s3_uri(s, settings)
            except Exception:
                signed = None
            return signed
        return None

    def _is_resolvable_listing_image(value: object) -> bool:
        return _to_http_image_url(value) is not None

    def _normalize_listing_media(record: dict) -> dict:
        record = _hydrate_listing_owner_name(db, record)
        image = record.get("image")
        images = record.get("images") or []
        normalized_image = _to_http_image_url(image)
        normalized_gallery: list[str] = []
        seen_image_keys: set[str] = set()
        if isinstance(images, list):
            for img in images:
                resolved = _to_http_image_url(img)
                key = _image_url_dedupe_key(resolved)
                if resolved and key not in seen_image_keys:
                    normalized_gallery.append(resolved)
                    seen_image_keys.add(key)
        if normalized_image:
            record["image"] = normalized_image
        if normalized_gallery:
            record["images"] = normalized_gallery
        has_valid_image = _is_resolvable_listing_image(record.get("image"))
        has_valid_gallery = (
            isinstance(record.get("images"), list)
            and any(_is_resolvable_listing_image(img) for img in (record.get("images") or []))
        )
        if not (has_valid_image or has_valid_gallery):
            record["image"] = None
            record["images"] = []
        return record

    safe_limit = max(1, min(limit, 100))
    safe_offset = max(0, offset)
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    try:
        stale_count = db.mark_stale_analyzing_listings_failed(cutoff)
        if stale_count:
            log_json("stale_analyzing_listings_marked_failed", count=stale_count, cutoff=cutoff)
    except Exception as exc:
        log_json("stale_analyzing_cleanup_error", error=str(exc))
    records = (
        db.list_owner_listings(principal.subject, limit=safe_limit + 1, offset=safe_offset)
        if mine
        else db.list_recent_listings(limit=safe_limit + 1, offset=safe_offset, include_analysis=False, include_media=True, active_only=True)
    )
    has_more = len(records) > safe_limit
    records = records[:safe_limit]
    records = [_normalize_listing_media(record) for record in records]

    if include_matches and not mine:
        viewer_size_prefs = _profile_size_preferences(db.get_user_profile_quiz(principal.subject))
        sent_offer_pairs = _sent_offer_match_pairs(db, principal.subject)
        my_active = [
            _normalize_listing_media(x)
            for x in db.list_owner_listings(principal.subject, limit=200)
            if str(x.get("status", "")).lower() == "active"
        ]
        for record in records:
            if not _listing_matches_viewer_size_preferences(record, viewer_size_prefs):
                record["matches"] = []
                continue
            base_value = float(record.get("estimated_value") or 0)
            if base_value <= 0:
                record["matches"] = []
                continue
            # Keep marketplace "matches" aligned with offer-candidate rules so
            # clicking Start Trade does not lead to zero eligible listings.
            tolerance, _ = _trade_match_tolerance(base_value)
            owner_subject = str(record.get("owner_subject") or "")
            owner_name = str(record.get("owner_name") or "").strip().lower()
            matches: list[dict] = []
            for candidate in my_active:
                if str(candidate.get("listing_id") or "") == str(record.get("listing_id") or ""):
                    continue
                if (str(record.get("listing_id") or ""), str(candidate.get("listing_id") or "")) in sent_offer_pairs:
                    continue
                candidate_owner_subject = str(candidate.get("owner_subject") or "")
                candidate_owner_name = str(candidate.get("owner_name") or "").strip().lower()
                if owner_subject and candidate_owner_subject and owner_subject == candidate_owner_subject:
                    # Never return same-owner listings as matches.
                    continue
                if (
                    (not owner_subject or not candidate_owner_subject)
                    and owner_name
                    and candidate_owner_name
                    and owner_name == candidate_owner_name
                ):
                    # Older records may be missing a stable subject; still avoid same-owner matches.
                    continue
                candidate_value = float(candidate.get("estimated_value") or 0)
                if candidate_value <= 0:
                    continue
                if abs(candidate_value - base_value) > tolerance:
                    continue
                matches.append(candidate)
                if len(matches) >= 12:
                    break
            record["matches"] = matches
    return {
        "count": len(records),
        "limit": safe_limit,
        "offset": safe_offset,
        "next_offset": safe_offset + len(records) if has_more else None,
        "has_more": has_more,
        "items": records,
        "actor": {"auth_type": principal.auth_type, "subject": principal.subject},
    }


@app.get("/v1/listings/{listing_id}/offer-candidates")
def list_offer_candidates(
    listing_id: str,
    limit: int = 100,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    def _to_http_image_url(value: object) -> str | None:
        normalized_public_url = _normalize_public_image_url(value)
        if normalized_public_url:
            return normalized_public_url
        s = value.strip() if isinstance(value, str) else ""
        if s.startswith("s3://"):
            try:
                signed = _presign_s3_uri(s, settings)
            except Exception:
                signed = None
            return signed
        return None

    def _normalize_listing_media(record: dict) -> dict:
        record = _hydrate_listing_owner_name(db, record)
        image = record.get("image")
        images = record.get("images") or []
        normalized_image = _to_http_image_url(image)
        normalized_gallery: list[str] = []
        seen_image_keys: set[str] = set()
        if isinstance(images, list):
            for img in images:
                resolved = _to_http_image_url(img)
                key = _image_url_dedupe_key(resolved)
                if resolved and key not in seen_image_keys:
                    normalized_gallery.append(resolved)
                    seen_image_keys.add(key)
        if normalized_image:
            record["image"] = normalized_image
        if normalized_gallery:
            record["images"] = normalized_gallery
        if not normalized_image and not normalized_gallery:
            record["image"] = None
            record["images"] = []
        return record

    target = db.get_listing_by_id(listing_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target listing not found")
    if str(target.get("owner_subject") or "") == principal.subject:
        raise HTTPException(status_code=400, detail="Cannot create a trade offer on your own listing")

    target_value = float(target.get("estimated_value") or 0)
    if target_value <= 0:
        return {"count": 0, "items": []}
    viewer_size_prefs = _profile_size_preferences(db.get_user_profile_quiz(principal.subject))
    if not _listing_matches_viewer_size_preferences(target, viewer_size_prefs):
        return {"count": 0, "items": []}

    tolerance, _ = _trade_match_tolerance(target_value)
    safe_limit = max(1, min(limit, 200))
    mine = db.list_owner_listings(principal.subject, limit=safe_limit)
    sent_offer_pairs = _sent_offer_match_pairs(db, principal.subject)
    candidates: list[dict] = []
    for record in mine:
        if str(record.get("status") or "").lower() != "active":
            continue
        if str(record.get("listing_id") or "") == str(target.get("listing_id") or ""):
            continue
        if (str(target.get("listing_id") or ""), str(record.get("listing_id") or "")) in sent_offer_pairs:
            continue
        cand_value = float(record.get("estimated_value") or 0)
        if cand_value <= 0:
            continue
        if abs(cand_value - target_value) > tolerance:
            continue
        candidates.append(_normalize_listing_media(record))

    return {"count": len(candidates), "items": candidates}


def _hydrate_trade_matches(db: Database, matches: list[dict]) -> list[TradeMatchResponse]:
    listing_ids: list[str] = []
    for match in matches:
        listing_ids.extend([
            str(match.get("target_listing_id") or ""),
            str(match.get("candidate_listing_id") or ""),
        ])
    listing_map = db.get_listings_by_ids(listing_ids)
    hydrated: list[TradeMatchResponse] = []
    for match in matches:
        target = listing_map.get(str(match.get("target_listing_id") or ""))
        candidate = listing_map.get(str(match.get("candidate_listing_id") or ""))
        if target:
            target = _hydrate_listing_owner_name(db, target)
        if candidate:
            candidate = _hydrate_listing_owner_name(db, candidate)
        hydrated.append(
            TradeMatchResponse(
                **match,
                target_listing=ListingResponse(**target) if target else None,
                candidate_listing=ListingResponse(**candidate) if candidate else None,
            )
        )
    return hydrated


@app.post("/v1/trade-match-agent/run", response_model=TradeMatchRunResponse)
def run_trade_match_agent(
    limit: int = 50,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not settings.trade_match_agent_enabled:
        return TradeMatchRunResponse(status="disabled", generated_count=0, items=[])
    safe_limit = max(1, min(limit, 200))
    max_targets = min(settings.trade_match_agent_max_targets, max(safe_limit * 4, safe_limit))
    marketplace = db.list_recent_listings(limit=max_targets, include_analysis=False, include_media=True, active_only=True)
    mine = [
        item
        for item in db.list_owner_listings(principal.subject, limit=settings.trade_match_agent_max_user_items)
        if str(item.get("status") or "").casefold() == "active"
    ]
    suggestions = build_trade_match_suggestions(
        viewer_subject=principal.subject,
        marketplace_listings=marketplace,
        viewer_active_listings=mine,
        viewer_profile=db.get_user_profile_quiz(principal.subject),
        max_matches_per_target=settings.trade_match_agent_max_matches_per_listing,
        max_total=safe_limit,
    )
    expired_count = db.expire_suggested_trade_matches(principal.subject)
    records = [
        {
            "match_id": str(uuid.uuid4()),
            "viewer_subject": principal.subject,
            "target_listing_id": suggestion.target_listing_id,
            "candidate_listing_id": suggestion.candidate_listing_id,
            "score": suggestion.score,
            "confidence": suggestion.confidence,
            "rationale": suggestion.rationale,
            "risk_flags": suggestion.risk_flags,
            "status": "suggested",
            "agent_version": suggestion.agent_version,
        }
        for suggestion in suggestions
    ]
    saved = db.upsert_trade_matches(records)
    return TradeMatchRunResponse(
        generated_count=len(saved),
        expired_count=expired_count,
        items=_hydrate_trade_matches(db, saved),
    )


@app.get("/v1/trade-match-agent/matches", response_model=TradeMatchListResponse)
def list_trade_match_agent_matches(
    limit: int = 50,
    status: str | None = "suggested",
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not settings.trade_match_agent_enabled:
        return TradeMatchListResponse(count=0, items=[])
    safe_limit = max(1, min(limit, 200))
    status_filter = status if status in {"suggested", "dismissed", "offered", "expired"} else "suggested"
    records = db.list_trade_matches(principal.subject, limit=safe_limit, status=status_filter)
    items = _hydrate_trade_matches(db, records)
    return TradeMatchListResponse(count=len(items), items=items)


@app.patch("/v1/trade-match-agent/matches/{match_id}", response_model=TradeMatchResponse)
def update_trade_match_agent_match(
    match_id: str,
    payload: TradeMatchStatusUpdateRequest,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not settings.trade_match_agent_enabled:
        raise HTTPException(status_code=404, detail="Trade match agent is disabled")
    updated = db.set_trade_match_status(
        match_id=match_id,
        viewer_subject=principal.subject,
        status=payload.status,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Trade match not found")
    return _hydrate_trade_matches(db, [updated])[0]


@app.put("/v1/listings/{listing_id}", response_model=ListingResponse)
def update_listing(
    listing_id: str,
    payload: ListingCreateRequest,
    background_tasks: BackgroundTasks,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
    valuation_service: ValuationService = Depends(get_valuation_service),
    gpt_item_profiler=Depends(get_gpt_item_profiler),
):
    previous_record = next((r for r in db.list_owner_listings(principal.subject, limit=500) if r["listing_id"] == listing_id), None)
    normalized_image, normalized_images = _normalize_listing_media_for_storage(
        db=db,
        image=payload.image,
        images=_listing_storage_images(payload.images, payload.analysis, payload.listed_images),
        source_item_id=payload.source_item_id,
    )
    updated = db.update_listing(
        listing_id=listing_id,
        owner_subject=principal.subject,
        title=payload.title,
        mode="trade",
        category=payload.category,
        brand=payload.brand,
        condition=payload.condition,
        size=payload.size,
        estimated_value=payload.estimated_value,
        city=payload.city,
        image=normalized_image,
        images=normalized_images,
        description=payload.description,
        wants=payload.wants,
        tags=payload.tags,
        source_item_id=payload.source_item_id,
        analysis=payload.analysis,
        status=payload.status,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="listing not found")
    record = next((r for r in db.list_owner_listings(principal.subject, limit=500) if r["listing_id"] == listing_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail="listing not found")
    if str(payload.status or "").lower() == "analyzing":
        previous_images = previous_record.get("images") if isinstance(previous_record, dict) and isinstance(previous_record.get("images"), list) else []
        if not previous_images and isinstance(previous_record, dict) and isinstance(previous_record.get("image"), str) and previous_record.get("image"):
            previous_images = [str(previous_record["image"])]
        stage_images_after_analysis = not _same_listing_image_urls(previous_images, _display_image_urls_from_storage_images(normalized_images))
        files = _collect_listing_analysis_files(db=db, settings=settings, listing=record)
        if files:
            background_tasks.add_task(
                _run_listing_analysis_job,
                listing_id=listing_id,
                owner_subject=principal.subject,
                files=files,
                category=payload.category,
                item_size=payload.size,
                user_condition=payload.condition,
                item_description=payload.description,
                debug=True,
                settings=settings,
                valuation_service=valuation_service,
                gpt_item_profiler=gpt_item_profiler,
                stage_images_after_analysis=stage_images_after_analysis,
            )
            log_json(
                "listing_analysis_auto_queued",
                listing_id=listing_id,
                actor=principal.subject,
                image_count=len(files),
                source="update_listing",
                stage_images_after_analysis=stage_images_after_analysis,
            )
        else:
            _mark_listing_analysis_failed(db, record, principal.subject)
            record = next((r for r in db.list_owner_listings(principal.subject, limit=500) if r["listing_id"] == listing_id), record)
            log_json("listing_analysis_auto_queue_no_files", listing_id=listing_id, actor=principal.subject, source="update_listing")
    return ListingResponse(**record)


@app.delete("/v1/listings/{listing_id}")
def delete_listing(
    listing_id: str,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
):
    record = db.get_listing_by_id(listing_id)
    if not record or str(record.get("owner_subject") or "") != principal.subject:
        raise HTTPException(status_code=404, detail="listing not found")
    if db.listing_has_active_trade(listing_id):
        raise HTTPException(status_code=409, detail="Listing is part of an active trade and cannot be removed.")
    deleted = db.delete_listing(listing_id=listing_id, owner_subject=principal.subject)
    if not deleted:
        raise HTTPException(status_code=404, detail="listing not found")
    return {"status": "deleted", "listing_id": listing_id}


@app.post("/v1/offers", response_model=OfferResponse)
def create_offer(
    payload: OfferCreateRequest,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    offered_ids = [x for x in (payload.offered_listing_ids or []) if isinstance(x, str) and x.strip()]
    if payload.offered_listing_id and payload.offered_listing_id.strip():
        offered_ids.append(payload.offered_listing_id.strip())
    offered_ids = list(dict.fromkeys(offered_ids))
    if not offered_ids:
        raise HTTPException(status_code=400, detail="At least one offered listing is required")
    if payload.target_listing_id in offered_ids:
        raise HTTPException(status_code=400, detail="Target listing cannot be included in offered listings")
    target = db.get_listing_by_id(payload.target_listing_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target listing not found")
    if target["owner_subject"] == principal.subject:
        raise HTTPException(status_code=400, detail="Cannot create a trade offer on your own listing")
    if not _subject_has_complete_shipping_address(db, principal.subject, settings):
        raise HTTPException(status_code=400, detail="Add a complete shipping address in Profile before sending a trade offer")
    if str(target.get("status", "")).lower() != "active":
        raise HTTPException(status_code=400, detail="Target listing is not active")
    target_value = float(target.get("estimated_value") or 0)
    if target_value <= 0:
        raise HTTPException(status_code=400, detail="Target listing must have a valid estimated value")
    tolerance, _ = _trade_match_tolerance(target_value)
    for offered_id in offered_ids:
        offered = db.get_listing_by_id(offered_id)
        if not offered:
            raise HTTPException(status_code=404, detail=f"Offered listing not found: {offered_id}")
        if offered["owner_subject"] != principal.subject:
            raise HTTPException(status_code=403, detail="You can only offer your own listings")
        if str(offered.get("status", "")).lower() != "active":
            raise HTTPException(status_code=400, detail="All offered listings must be active")
        offered_value = float(offered.get("estimated_value") or 0)
        if offered_value <= 0:
            raise HTTPException(status_code=400, detail="All offered listings must have a valid estimated value")
        if abs(offered_value - target_value) > tolerance:
            raise HTTPException(status_code=400, detail="Each offered listing must be within the trade price band")

    offer = db.create_trade_offer(
        offer_id=str(uuid.uuid4()),
        target_listing_id=payload.target_listing_id,
        offered_listing_id=offered_ids[0],
        offered_listing_ids=offered_ids,
        from_subject=principal.subject,
        to_subject=target["owner_subject"],
        from_receive_address=_profile_primary_shipping_address_for_offer(db, principal.subject, settings),
        message=(payload.message or "").strip(),
    )
    offer["from_name"] = _profile_subject_first_name(db, offer.get("from_subject"))
    offer["to_name"] = _profile_subject_first_name(db, offer.get("to_subject"))
    return OfferResponse(**offer)


@app.get("/v1/offers/incoming")
def list_incoming_offers(
    status: str = "pending",
    limit: int = 50,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
):
    allowed_status = {"pending", "accepted", "declined", "countered", "cancelled", "all"}
    status_norm = (status or "pending").strip().lower()
    if status_norm not in allowed_status:
        raise HTTPException(status_code=400, detail="Invalid status filter")
    filter_status = None if status_norm == "all" else status_norm
    offers = db.list_trade_offers_for_subject(principal.subject, limit=limit, status=filter_status)
    listing_ids: list[str] = []
    for offer in offers:
        target_id = str(offer.get("target_listing_id") or "").strip()
        if target_id:
            listing_ids.append(target_id)
        offered_ids = [x for x in (offer.get("offered_listing_ids") or []) if isinstance(x, str) and x.strip()]
        if not offered_ids and isinstance(offer.get("offered_listing_id"), str):
            offered_ids = [offer["offered_listing_id"]]
        listing_ids.extend(offered_ids)
        selected_offered_id = str(offer.get("selected_offered_listing_id") or "").strip()
        if selected_offered_id:
            listing_ids.append(selected_offered_id)
    listing_map = db.get_listings_by_ids(listing_ids)
    items: list[OfferWithListingsResponse] = []
    for offer in offers:
        target = listing_map.get(str(offer["target_listing_id"]))
        offered_ids = [x for x in (offer.get("offered_listing_ids") or []) if isinstance(x, str) and x.strip()]
        offered_listings = [listing_map.get(str(x)) for x in offered_ids]
        offered_listings = [x for x in offered_listings if x]
        selected_offered_id = str(offer.get("selected_offered_listing_id") or "").strip()
        offered = listing_map.get(selected_offered_id) if selected_offered_id else None
        offered = offered or (offered_listings[0] if offered_listings else listing_map.get(str(offer["offered_listing_id"])))
        if not target or not offered:
            continue
        items.append(
            OfferWithListingsResponse(
                offer_id=offer["offer_id"],
                target_listing_id=offer["target_listing_id"],
                offered_listing_id=offer["offered_listing_id"],
                offered_listing_ids=offered_ids or [offer["offered_listing_id"]],
                selected_offered_listing_id=offer.get("selected_offered_listing_id"),
                from_subject=offer["from_subject"],
                to_subject=offer["to_subject"],
                from_name=_profile_subject_first_name(db, offer.get("from_subject")),
                to_name=_profile_subject_first_name(db, offer.get("to_subject")),
                status=offer["status"],
                message=offer.get("message") or "",
                created_at=offer["created_at"],
                updated_at=offer["updated_at"],
                target_listing=ListingResponse(**target),
                offered_listing=ListingResponse(**offered),
                offered_listings=[ListingResponse(**x) for x in offered_listings] if offered_listings else [ListingResponse(**offered)],
            )
        )
    return {
        "count": len(items),
        "items": [item.model_dump() for item in items],
        "actor": {"auth_type": principal.auth_type, "subject": principal.subject},
    }


@app.post("/v1/offers/{offer_id}/action", response_model=OfferResponse)
def action_offer(
    offer_id: str,
    payload: OfferActionRequest,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    offer = db.get_trade_offer_by_id(offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    if principal.subject not in {offer.get("from_subject"), offer.get("to_subject")}:
        raise HTTPException(status_code=403, detail="Forbidden")
    if payload.status == "accepted" and principal.subject == str(offer.get("from_subject") or ""):
        raise HTTPException(status_code=400, detail="Sender is already marked ready. Only the receiver needs to accept.")
    if payload.status == "accepted" and not _subject_has_complete_shipping_address(db, principal.subject, settings):
        raise HTTPException(status_code=400, detail="Add a complete shipping address in Profile before accepting trade")
    if payload.status == "accepted" and payload.receive_address is None:
        raise HTTPException(status_code=400, detail="Select receive shipping address while accepting trade")
    if payload.status == "accepted" and principal.subject == str(offer.get("to_subject") or ""):
        offered_ids = [x for x in (offer.get("offered_listing_ids") or []) if isinstance(x, str) and x.strip()]
        if not offered_ids and isinstance(offer.get("offered_listing_id"), str) and offer["offered_listing_id"].strip():
            offered_ids = [offer["offered_listing_id"].strip()]
        selected_offered_id = str(payload.selected_offered_listing_id or "").strip()
        if not selected_offered_id and len(offered_ids) == 1:
            selected_offered_id = offered_ids[0]
        if selected_offered_id not in offered_ids:
            raise HTTPException(status_code=400, detail="Select one offered item to accept for this trade")
    receive_address_payload = payload.receive_address.model_dump() if payload.receive_address else None
    updated = db.set_trade_offer_participant_action(
        offer_id=offer_id,
        actor_subject=principal.subject,
        status=payload.status,
        receive_address=receive_address_payload,
        selected_offered_listing_id=payload.selected_offered_listing_id,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Offer not found")
    if str(updated.get("status") or "").lower() == "accepted":
        accepted_offered_id = str(updated.get("selected_offered_listing_id") or updated.get("offered_listing_id") or "").strip()
        db.mark_listings_traded([updated["target_listing_id"], accepted_offered_id])
        try:
            _auto_create_labels_for_accepted_offer_and_notify(db=db, offer=updated, settings=settings)
        except Exception:
            # Do not block offer acceptance if shipping providers/email providers are temporarily unavailable.
            pass
    updated["from_name"] = _profile_subject_first_name(db, updated.get("from_subject"))
    updated["to_name"] = _profile_subject_first_name(db, updated.get("to_subject"))
    return OfferResponse(**updated)


def _subject_shipping_snapshot(db: Database, subject: str, settings: Settings | None = None) -> dict[str, str | None]:
    p = db.get_user_profile_quiz(subject) or {}
    shipping_name = (p.get("shipping_full_name") or "").strip() if isinstance(p.get("shipping_full_name"), str) else ""
    if not shipping_name:
        listings = db.list_recent_listings(limit=5000, include_analysis=False, include_media=False)
        for listing in listings:
            if str(listing.get("owner_subject") or "") == subject:
                candidate = listing.get("owner_name")
                if isinstance(candidate, str) and candidate.strip():
                    shipping_name = candidate.strip()
                    break
    return {
        "name": shipping_name or None,
        "line1": p.get("shipping_address_line1"),
        "line2": p.get("shipping_address_line2"),
        "city": p.get("shipping_city"),
        "state": p.get("shipping_state"),
        "postal": p.get("shipping_postal_code"),
        "country": p.get("shipping_country") or "US",
        "email": (p.get("shipping_email") if p.get("shipping_email") else (settings.shippo_default_contact_email if settings else None)),
        "phone": (p.get("shipping_phone") if p.get("shipping_phone") else (settings.shippo_default_contact_phone if settings else None)),
    }


def _receive_address_snapshot_from_offer(*, offer: dict, subject: str, db: Database, settings: Settings) -> dict[str, str | None]:
    key = "from_receive_address" if subject == str(offer.get("from_subject") or "") else "to_receive_address"
    raw = offer.get(key)
    if isinstance(raw, dict):
        return {
            "name": (raw.get("full_name") if isinstance(raw.get("full_name"), str) else None),
            "line1": (raw.get("address_line1") if isinstance(raw.get("address_line1"), str) else None),
            "line2": (raw.get("address_line2") if isinstance(raw.get("address_line2"), str) else None),
            "city": (raw.get("city") if isinstance(raw.get("city"), str) else None),
            "state": (raw.get("state") if isinstance(raw.get("state"), str) else None),
            "postal": (raw.get("postal_code") if isinstance(raw.get("postal_code"), str) else None),
            "country": (raw.get("country") if isinstance(raw.get("country"), str) else "US"),
            "email": None,
            "phone": None,
        }
    return _subject_shipping_snapshot(db, subject, settings)


def _profile_primary_shipping_address_for_offer(db: Database, subject: str, settings: Settings) -> dict[str, object] | None:
    snapshot = _subject_shipping_snapshot(db, subject, settings)
    if not _address_complete(snapshot):
        return None
    return {
        "full_name": snapshot.get("name"),
        "address_line1": snapshot.get("line1"),
        "address_line2": snapshot.get("line2"),
        "city": snapshot.get("city"),
        "state": snapshot.get("state"),
        "postal_code": snapshot.get("postal"),
        "country": snapshot.get("country") or "US",
        "is_default": True,
    }


def _outbound_leg_for_subject(offer: dict, subject: str) -> tuple[str, str, str, str]:
    from_subject_offer = str(offer.get("from_subject") or "")
    to_subject_offer = str(offer.get("to_subject") or "")
    offered_ids = [x for x in (offer.get("offered_listing_ids") or []) if isinstance(x, str) and x.strip()]
    if not offered_ids and isinstance(offer.get("offered_listing_id"), str):
        offered_ids = [offer["offered_listing_id"]]
    selected_offered_id = str(offer.get("selected_offered_listing_id") or "").strip()
    if selected_offered_id in offered_ids:
        offered_ids = [selected_offered_id]
    target_listing_id = str(offer.get("target_listing_id") or "")
    if subject == from_subject_offer:
        return from_subject_offer, to_subject_offer, (offered_ids[0] if offered_ids else ""), target_listing_id
    return to_subject_offer, from_subject_offer, target_listing_id, (offered_ids[0] if offered_ids else "")


def _estimated_shipping_weight_oz_from_listing(listing: dict | None, settings: Settings) -> float:
    if isinstance(listing, dict):
        analysis = listing.get("analysis") if isinstance(listing.get("analysis"), dict) else {}
        profile = analysis.get("item_profile") if isinstance(analysis.get("item_profile"), dict) else {}
        shipping_profile = profile.get("shipping_profile") if isinstance(profile.get("shipping_profile"), dict) else {}
        weight = shipping_profile.get("estimated_weight_oz")
        if isinstance(weight, (int, float)):
            numeric = float(weight)
            if 1 <= numeric <= 240:
                return numeric
        if isinstance(weight, str):
            match = re.search(r"(\d+(?:\.\d+)?)", weight.lower())
            if match:
                numeric = float(match.group(1))
                if "lb" in weight.lower() or "pound" in weight.lower():
                    numeric *= 16
                if 1 <= numeric <= 240:
                    return numeric
    return float(settings.shippo_parcel_weight_oz)


def _hydrate_shipment_party_fields(db: Database, shipment: dict) -> dict:
    hydrated = dict(shipment)
    from_snapshot = _subject_shipping_snapshot(db, str(shipment.get("from_subject") or ""))
    to_snapshot = _subject_shipping_snapshot(db, str(shipment.get("to_subject") or ""))
    mapping = (
        ("from_name", "name", from_snapshot),
        ("from_address_line1", "line1", from_snapshot),
        ("from_address_line2", "line2", from_snapshot),
        ("from_city", "city", from_snapshot),
        ("from_state", "state", from_snapshot),
        ("from_postal_code", "postal", from_snapshot),
        ("from_country", "country", from_snapshot),
        ("to_name", "name", to_snapshot),
        ("to_address_line1", "line1", to_snapshot),
        ("to_address_line2", "line2", to_snapshot),
        ("to_city", "city", to_snapshot),
        ("to_state", "state", to_snapshot),
        ("to_postal_code", "postal", to_snapshot),
        ("to_country", "country", to_snapshot),
    )
    for out_key, src_key, snapshot in mapping:
        current = hydrated.get(out_key)
        if isinstance(current, str) and current.strip():
            continue
        replacement = snapshot.get(src_key)
        if isinstance(replacement, str) and replacement.strip():
            hydrated[out_key] = replacement.strip()
        elif out_key.endswith("_country") and not current:
            hydrated[out_key] = "US"

    # Fallback to listing owners for names when profile-based name is unavailable.
    if not (isinstance(hydrated.get("from_name"), str) and hydrated.get("from_name", "").strip()):
        from_listing = db.get_listing_by_id(str(shipment.get("from_listing_id") or ""))
        from_owner = (from_listing or {}).get("owner_name")
        if isinstance(from_owner, str) and from_owner.strip():
            hydrated["from_name"] = from_owner.strip()
    if not (isinstance(hydrated.get("to_name"), str) and hydrated.get("to_name", "").strip()):
        to_listing = db.get_listing_by_id(str(shipment.get("to_listing_id") or ""))
        to_owner = (to_listing or {}).get("owner_name")
        if isinstance(to_owner, str) and to_owner.strip():
            hydrated["to_name"] = to_owner.strip()
    return hydrated


def _visible_shipments_for_subject(*, shipments: list[dict], subject: str) -> list[dict]:
    actor = str(subject or "")
    return [s for s in shipments if str(s.get("from_subject") or "") == actor]


def _address_complete(a: dict[str, str | None]) -> bool:
    return bool(
        (a.get("name") or "").strip()
        and (a.get("line1") or "").strip()
        and (a.get("city") or "").strip()
        and (a.get("state") or "").strip()
        and (a.get("postal") or "").strip()
        and (a.get("country") or "").strip()
    )


def _subject_has_complete_shipping_address(db: Database, subject: str, settings: Settings | None = None) -> bool:
    return _address_complete(_subject_shipping_snapshot(db, subject, settings))


def _contact_complete(a: dict[str, str | None]) -> bool:
    return bool((a.get("email") or "").strip() and (a.get("phone") or "").strip())


def _parse_iso_dt(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        normalized = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _shippo_carrier_token(carrier: str | None) -> str:
    raw = str(carrier or "").strip().lower()
    aliases = {
        "usps": "usps",
        "united states postal service": "usps",
        "ups": "ups",
        "fedex": "fedex",
        "dhl express": "dhl_express",
        "dhl": "dhl_express",
    }
    return aliases.get(raw, raw.replace(" ", "_"))


def _shippo_tracking_snapshot(*, settings: Settings, carrier: str | None, tracking_number: str | None) -> dict | None:
    key = (settings.shippo_api_key or "").strip()
    carrier_raw = str(carrier or "").strip()
    tracking_raw = str(tracking_number or "").strip()
    if not key or not carrier_raw or not tracking_raw:
        return None
    carrier_token = _shippo_carrier_token(carrier_raw)
    base = settings.shippo_api_base_url.rstrip("/")
    headers = {"Authorization": f"ShippoToken {key}"}
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(f"{base}/tracks/{carrier_token}/{tracking_raw}", headers=headers)
        if resp.status_code >= 400:
            return None
        body = resp.json() if resp.content else {}
        status_obj = body.get("tracking_status") if isinstance(body, dict) else None
        if not isinstance(status_obj, dict):
            status_obj = {}
        status_code = str(status_obj.get("status") or body.get("tracking_status") or "").strip().upper()
        status_map = {
            "UNKNOWN": "label_created",
            "PRE_TRANSIT": "label_created",
            "TRANSIT": "shipped",
            "OUT_FOR_DELIVERY": "out_for_delivery",
            "DELIVERED": "delivered",
            "RETURNED": "returned",
            "FAILURE": "exception",
        }
        events = body.get("tracking_history") if isinstance(body, dict) else []
        history = []
        if isinstance(events, list):
            for event in events[:20]:
                if not isinstance(event, dict):
                    continue
                history.append({
                    "status": str(event.get("status") or "").strip(),
                    "status_details": str(event.get("status_details") or "").strip(),
                    "status_date": str(event.get("status_date") or "").strip(),
                    "location": str(event.get("location") or "").strip(),
                })
        return {
            "status": status_map.get(status_code, "label_created"),
            "tracking_status": status_code.lower(),
            "tracking_status_details": str(status_obj.get("status_details") or "").strip() or None,
            "tracking_status_updated_at": str(status_obj.get("status_date") or "").strip() or None,
            "tracking_eta": str(body.get("eta") or "").strip() or None,
            "tracking_history": history,
        }
    except Exception:
        return None


def _tracking_status_label(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    labels = {
        "label_created": "Label created",
        "pre_transit": "Label created",
        "shipped": "In transit",
        "transit": "In transit",
        "out_for_delivery": "Out for delivery",
        "delivered": "Delivered",
        "returned": "Returned",
        "exception": "Delivery exception",
    }
    return labels.get(normalized, normalized.replace("_", " ").title() if normalized else "Tracking updated")


def _send_tracking_update_email_if_configured(
    *,
    settings: Settings,
    to_email: str | None,
    customer_name: str | None,
    offer_id: str,
    tracking_number: str | None,
    carrier: str | None,
    service_level: str | None,
    status_label: str,
    status_details: str | None = None,
    tracking_eta: str | None = None,
) -> str:
    recipient = str(to_email or "").strip()
    if not recipient:
        return "skipped_no_recipient"

    subject = f"Shipping update: {status_label}"
    optional_lines: list[str] = []
    if status_details:
        optional_lines.append(f"Details: {status_details}")
    if tracking_eta:
        optional_lines.append(f"Estimated delivery: {tracking_eta}")
    optional_text = ("\n".join(optional_lines) + "\n") if optional_lines else ""
    text_body = (
        f"Hi {customer_name or 'there'},\n\n"
        f"Shipping status for offer {offer_id}: {status_label}.\n"
        f"Carrier: {carrier or 'USPS'}\n"
        f"Service: {service_level or 'Priority Mail'}\n"
        f"Tracking: {tracking_number or 'pending'}\n"
        f"{optional_text}"
    )

    def _send_via_ses(recipient_email: str) -> str:
        from_email = str(settings.ses_from_email or settings.smtp_from_email or "").strip()
        template_name = str(settings.ses_template_shipping_tracking_update or "").strip()
        region = str(settings.ses_region or settings.aws_region or "us-east-1").strip()
        if not from_email:
            return "skipped_ses_not_configured"
        try:
            session = boto3.session.Session(
                aws_access_key_id=(settings.ses_access_key_id or None),
                aws_secret_access_key=(settings.ses_secret_access_key or None),
                aws_session_token=(settings.ses_session_token or None),
                region_name=region,
            )
            client = session.client("ses", endpoint_url=(settings.ses_endpoint_url or None))
            if template_name:
                client.send_templated_email(
                    Source=from_email,
                    Destination={"ToAddresses": [recipient_email]},
                    Template=template_name,
                    TemplateData=json.dumps({
                        "customer_name": str(customer_name or "there"),
                        "offer_id": str(offer_id or ""),
                        "tracking_number": str(tracking_number or ""),
                        "carrier": str(carrier or "USPS"),
                        "service_level": str(service_level or "Priority Mail"),
                        "status_label": status_label,
                        "status_details": str(status_details or ""),
                        "tracking_eta": str(tracking_eta or ""),
                    }),
                )
            else:
                client.send_email(
                    Source=from_email,
                    Destination={"ToAddresses": [recipient_email]},
                    Message={
                        "Subject": {"Data": subject, "Charset": "UTF-8"},
                        "Body": {"Text": {"Data": text_body, "Charset": "UTF-8"}},
                    },
                )
            return "sent_ses"
        except Exception:
            return "failed_ses"

    def _send_via_smtp(recipient_email: str) -> str:
        host = str(settings.smtp_host or "").strip()
        from_email = str(settings.smtp_from_email or settings.ses_from_email or "").strip()
        if not host or not from_email:
            return "skipped_smtp_not_configured"
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = recipient_email
        msg.set_content(text_body)
        try:
            with smtplib.SMTP(host, int(settings.smtp_port), timeout=20) as smtp:
                if settings.smtp_use_tls:
                    smtp.starttls()
                if settings.smtp_username:
                    smtp.login(settings.smtp_username, settings.smtp_password or "")
                smtp.send_message(msg)
            return "sent_smtp"
        except Exception:
            return "failed_smtp"

    provider = str(settings.email_provider or "auto").strip().lower()
    if provider == "ses":
        return _send_via_ses(recipient)
    if provider == "smtp":
        return _send_via_smtp(recipient)
    ses_result = _send_via_ses(recipient)
    if ses_result == "sent_ses":
        return ses_result
    smtp_result = _send_via_smtp(recipient)
    if smtp_result == "sent_smtp":
        return smtp_result
    if ses_result.startswith("failed"):
        return ses_result
    if smtp_result.startswith("failed"):
        return smtp_result
    return "skipped_not_configured"


def _notify_shipment_tracking_update(*, db: Database, settings: Settings, shipment: dict, previous_status: str | None, next_status: str | None) -> None:
    if str(previous_status or "").strip().lower() == str(next_status or "").strip().lower():
        return
    status_label = _tracking_status_label(next_status)
    offer_id = str(shipment.get("offer_id") or "")
    tracking_number = str(shipment.get("tracking_number") or "").strip()
    title = f"Shipment {status_label.lower()}"
    body = f"{shipment.get('carrier') or 'Carrier'} tracking {tracking_number or 'is'}: {status_label}."
    for owner_subject in {str(shipment.get("from_subject") or ""), str(shipment.get("to_subject") or "")}:
        if not owner_subject:
            continue
        db.create_user_notification(
            notification_id=str(uuid.uuid4()),
            owner_subject=owner_subject,
            actor_subject=str(shipment.get("from_subject") or "") or None,
            type="shipping-tracking",
            title=title,
            body=body,
            entity_id=offer_id,
            action_tab="inbox",
        )
        snapshot = _subject_shipping_snapshot(db, owner_subject, settings)
        email_status = _send_tracking_update_email_if_configured(
            settings=settings,
            to_email=snapshot.get("email"),
            customer_name=snapshot.get("name"),
            offer_id=offer_id,
            tracking_number=tracking_number,
            carrier=str(shipment.get("carrier") or ""),
            service_level=str(shipment.get("service_level") or ""),
            status_label=status_label,
            status_details=str(shipment.get("tracking_status_details") or "") or None,
            tracking_eta=str(shipment.get("tracking_eta") or "") or None,
        )
        log_json(
            "shipping_tracking_update_notified",
            shipment_id=shipment.get("shipment_id"),
            offer_id=offer_id,
            owner_subject=owner_subject,
            previous_status=previous_status,
            next_status=next_status,
            email_status=email_status,
        )


def _refresh_shipment_tracking_status(*, db: Database, settings: Settings, shipment: dict, notify: bool = True) -> dict:
    current_status = str(shipment.get("status") or "").strip().lower()
    if current_status in {"delivered", "cancelled"}:
        return shipment
    snapshot = _shippo_tracking_snapshot(
        settings=settings,
        carrier=str(shipment.get("carrier") or ""),
        tracking_number=str(shipment.get("tracking_number") or ""),
    )
    if not snapshot:
        return shipment
    tracked_status = str(snapshot.get("status") or "").strip().lower()
    if tracked_status in {"label_created", "shipped", "out_for_delivery", "delivered", "returned", "exception"}:
        previous_tracking_status = str(shipment.get("tracking_status") or shipment.get("status") or "").strip().lower()
        updated = db.update_trade_shipment_tracking(
            shipment_id=str(shipment.get("shipment_id") or ""),
            status=tracked_status,
            tracking_status=str(snapshot.get("tracking_status") or "").strip().lower() or None,
            tracking_status_details=snapshot.get("tracking_status_details"),
            tracking_status_updated_at=snapshot.get("tracking_status_updated_at"),
            tracking_eta=snapshot.get("tracking_eta"),
            tracking_history=snapshot.get("tracking_history") if isinstance(snapshot.get("tracking_history"), list) else [],
        )
        if updated:
            next_tracking_status = str(updated.get("tracking_status") or updated.get("status") or "").strip().lower()
            if notify:
                _notify_shipment_tracking_update(
                    db=db,
                    settings=settings,
                    shipment=updated,
                    previous_status=previous_tracking_status,
                    next_status=next_tracking_status,
                )
            return updated
    return shipment


def _shippo_quote_rate(
    *,
    settings: Settings,
    from_addr: dict[str, str | None],
    to_addr: dict[str, str | None],
    parcel_weight_oz: float | None = None,
) -> dict[str, str]:
    key = (settings.shippo_api_key or "").strip()
    if not key:
        return {"status": "awaiting_shippo_config", "carrier": "USPS", "service_level": "Priority Mail", "debug": "SHIPPO_API_KEY is not configured"}
    if not _address_complete(from_addr) or not _address_complete(to_addr):
        return {"status": "awaiting_address", "carrier": "USPS", "service_level": "Priority Mail", "debug": "from/to shipping address is incomplete"}
    if not _contact_complete(from_addr) or not _contact_complete(to_addr):
        return {"status": "awaiting_contact", "carrier": "USPS", "service_level": "Priority Mail", "debug": "from/to contact info (email + phone) is incomplete"}

    base = settings.shippo_api_base_url.rstrip("/")
    headers = {"Authorization": f"ShippoToken {key}", "Content-Type": "application/json"}
    package_weight_oz = float(parcel_weight_oz or settings.shippo_parcel_weight_oz)
    shipment_payload = {
        "address_from": {
            "name": from_addr.get("name"),
            "street1": from_addr.get("line1"),
            "street2": from_addr.get("line2") or "",
            "city": from_addr.get("city"),
            "state": from_addr.get("state"),
            "zip": from_addr.get("postal"),
            "country": from_addr.get("country") or "US",
            "email": from_addr.get("email"),
            "phone": from_addr.get("phone"),
        },
        "address_to": {
            "name": to_addr.get("name"),
            "street1": to_addr.get("line1"),
            "street2": to_addr.get("line2") or "",
            "city": to_addr.get("city"),
            "state": to_addr.get("state"),
            "zip": to_addr.get("postal"),
            "country": to_addr.get("country") or "US",
            "email": to_addr.get("email"),
            "phone": to_addr.get("phone"),
        },
        "parcels": [{
            "length": "12", "width": "10", "height": "6", "distance_unit": "in",
            "weight": str(package_weight_oz), "mass_unit": "oz",
        }],
        "async": False,
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            ship = client.post(f"{base}/shipments/", json=shipment_payload, headers=headers)
            if ship.status_code >= 400:
                return {"status": "shippo_shipment_error", "carrier": "USPS", "service_level": "Priority Mail", "debug": f"shipment_http_{ship.status_code}: {ship.text[:500]}"}
            rates = ship.json().get("rates") or []
            if not isinstance(rates, list) or not rates:
                return {"status": "shippo_no_rates", "carrier": "USPS", "service_level": "Priority Mail", "debug": f"shipment_has_no_rates: {ship.text[:500]}"}
            rates_sorted = sorted(rates, key=lambda r: float(r.get("amount") or 1e9))
            chosen = next((r for r in rates_sorted if str(r.get("provider") or "").lower() == "usps"), rates_sorted[0])
            rate_id = str(chosen.get("object_id") or "").strip()
            return {
                "status": "quoted",
                "carrier": str(chosen.get("provider") or "USPS"),
                "service_level": str((chosen.get("servicelevel") or {}).get("name") if isinstance(chosen.get("servicelevel"), dict) else (chosen.get("servicelevel") or "Priority Mail")),
                "amount": str(chosen.get("amount") or ""),
                "currency": str(chosen.get("currency") or "USD"),
                "rate_id": rate_id,
                "parcel_weight_oz": str(package_weight_oz),
            }
    except Exception:
        return {"status": "shippo_unavailable", "carrier": "USPS", "service_level": "Priority Mail", "debug": "exception while calling Shippo API"}


def _apply_shippo_flat_rate_quote(*, settings: Settings, quote: dict[str, str]) -> dict[str, str]:
    if str(quote.get("status") or "").lower() != "quoted":
        return quote
    if not bool(getattr(settings, "shippo_flat_rate_enabled", False)):
        return quote
    try:
        parcel_weight_oz = float(quote.get("parcel_weight_oz") or settings.shippo_parcel_weight_oz)
        max_weight_oz = float(settings.shippo_flat_rate_max_weight_oz)
    except (TypeError, ValueError):
        return quote
    if parcel_weight_oz > max_weight_oz:
        return quote

    real_amount = str(quote.get("amount") or "").strip()
    real_currency = str(quote.get("currency") or "").strip() or "USD"
    debug_parts = [str(quote.get("debug") or "").strip()] if quote.get("debug") else []
    if real_amount:
        debug_parts.append(f"shippo_rate={real_currency} {real_amount}")
    debug_parts.append(
        f"jouft_flat_rate={settings.shippo_flat_rate_currency} {settings.shippo_flat_rate_amount}; max_weight_oz={max_weight_oz:g}"
    )
    return {
        **quote,
        "amount": str(settings.shippo_flat_rate_amount),
        "currency": str(settings.shippo_flat_rate_currency or real_currency or "USD"),
        "debug": "; ".join(debug_parts),
    }


def _shippo_buy_label_from_rate(*, settings: Settings, rate_id: str) -> dict[str, str]:
    key = (settings.shippo_api_key or "").strip()
    if not key:
        return {"status": "awaiting_shippo_config", "carrier": "USPS", "service_level": "Priority Mail", "debug": "SHIPPO_API_KEY is not configured"}
    if not rate_id:
        return {"status": "shippo_no_rate_id", "carrier": "USPS", "service_level": "Priority Mail", "debug": "rate_id is required"}
    base = settings.shippo_api_base_url.rstrip("/")
    headers = {"Authorization": f"ShippoToken {key}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=20.0) as client:
            txn = client.post(f"{base}/transactions/", json={"rate": rate_id, "label_file_type": "PDF", "async": False}, headers=headers)
            if txn.status_code >= 400:
                return {"status": "shippo_transaction_error", "carrier": "USPS", "service_level": "Priority Mail", "debug": f"transaction_http_{txn.status_code}: {txn.text[:500]}"}
            tx = txn.json()
            tx_label_url = str(tx.get("label_url") or tx.get("label_url_pdf") or tx.get("label_file") or tx.get("label_file_url") or "").strip()
            tx_status = str(tx.get("status") or "").strip().upper()
            return {
                "status": ("label_created" if tx_label_url and tx_status in {"SUCCESS", "QUEUED", "WAITING"} else "awaiting_label_url"),
                "carrier": str(tx.get("carrier") or "USPS"),
                "service_level": str((tx.get("servicelevel") or {}).get("name") if isinstance(tx.get("servicelevel"), dict) else (tx.get("servicelevel") or "Priority Mail")),
                "tracking_number": str(tx.get("tracking_number") or ""),
                "label_url": tx_label_url,
                "debug": f"tx_status={tx_status or 'UNKNOWN'}; has_label_url={'yes' if tx_label_url else 'no'}",
            }
    except Exception:
        return {"status": "shippo_unavailable", "carrier": "USPS", "service_level": "Priority Mail", "debug": "exception while creating transaction"}


def _send_label_email_if_configured(
    *,
    settings: Settings,
    to_email: str | None,
    customer_name: str | None,
    offer_id: str,
    label_url: str,
    tracking_number: str | None = None,
    carrier: str | None = None,
    service_level: str | None = None,
) -> str:
    def _send_via_ses(recipient: str) -> str:
        from_email = str(settings.ses_from_email or settings.smtp_from_email or "").strip()
        template_name = str(settings.ses_template_shipping_label or "").strip()
        region = str(settings.ses_region or settings.aws_region or "us-east-1").strip()
        if not from_email:
            return "skipped_ses_not_configured"
        try:
            session = boto3.session.Session(
                aws_access_key_id=(settings.ses_access_key_id or None),
                aws_secret_access_key=(settings.ses_secret_access_key or None),
                aws_session_token=(settings.ses_session_token or None),
                region_name=region,
            )
            client = session.client("ses", endpoint_url=(settings.ses_endpoint_url or None))
            if template_name:
                template_data = {
                    "customer_name": str(customer_name or "there"),
                    "offer_id": str(offer_id or ""),
                    "label_url": str(label_url or ""),
                    "tracking_number": str(tracking_number or ""),
                    "carrier": str(carrier or "USPS"),
                    "service_level": str(service_level or "Priority Mail"),
                }
                client.send_templated_email(
                    Source=from_email,
                    Destination={"ToAddresses": [recipient]},
                    Template=template_name,
                    TemplateData=json.dumps(template_data),
                )
            else:
                client.send_email(
                    Source=from_email,
                    Destination={"ToAddresses": [recipient]},
                    Message={
                        "Subject": {"Data": f"Your ValueAI shipping label for offer {offer_id}", "Charset": "UTF-8"},
                        "Body": {
                            "Text": {
                                "Data": (
                                    "Your shipping label is ready.\n\n"
                                    f"Offer: {offer_id}\n"
                                    f"Label URL: {label_url}\n"
                                ),
                                "Charset": "UTF-8",
                            }
                        },
                    },
                )
            return "sent_ses"
        except Exception:
            return "failed_ses"

    def _send_via_smtp(recipient: str) -> str:
        host = str(settings.smtp_host or "").strip()
        from_email = str(settings.smtp_from_email or settings.ses_from_email or "").strip()
        if not host or not from_email:
            return "skipped_smtp_not_configured"
        msg = EmailMessage()
        msg["Subject"] = f"Your ValueAI shipping label for offer {offer_id}"
        msg["From"] = from_email
        msg["To"] = recipient
        msg.set_content(f"Your shipping label is ready.\n\nOffer: {offer_id}\nLabel URL: {label_url}\n")
        try:
            with smtplib.SMTP(host, int(settings.smtp_port), timeout=20) as smtp:
                if settings.smtp_use_tls:
                    smtp.starttls()
                if settings.smtp_username:
                    smtp.login(settings.smtp_username, settings.smtp_password or "")
                smtp.send_message(msg)
            return "sent_smtp"
        except Exception:
            return "failed_smtp"

    recipient = str(to_email or "").strip()
    if not recipient:
        return "skipped_no_recipient"
    provider = str(settings.email_provider or "auto").strip().lower()

    if provider == "ses":
        return _send_via_ses(recipient)
    if provider == "smtp":
        return _send_via_smtp(recipient)

    ses_result = _send_via_ses(recipient)
    if ses_result == "sent_ses":
        return ses_result
    smtp_result = _send_via_smtp(recipient)
    if smtp_result == "sent_smtp":
        return smtp_result
    if ses_result.startswith("failed"):
        return ses_result
    if smtp_result.startswith("failed"):
        return smtp_result
    return "skipped_not_configured"


def _send_shipping_reminder_email_if_configured(
    *,
    settings: Settings,
    to_email: str | None,
    customer_name: str | None,
    offer_id: str,
    label_url: str,
    tracking_number: str | None = None,
    carrier: str | None = None,
    service_level: str | None = None,
    reminder_count: int = 0,
) -> str:
    def _send_via_ses(recipient: str) -> str:
        from_email = str(settings.ses_from_email or settings.smtp_from_email or "").strip()
        template_name = str(settings.ses_template_shipping_reminder or "").strip()
        region = str(settings.ses_region or "us-east-1").strip()
        if not from_email:
            return "skipped_ses_not_configured"
        try:
            session = boto3.session.Session(
                aws_access_key_id=(settings.ses_access_key_id or None),
                aws_secret_access_key=(settings.ses_secret_access_key or None),
                aws_session_token=(settings.ses_session_token or None),
                region_name=region,
            )
            client = session.client("ses", endpoint_url=(settings.ses_endpoint_url or None))
            if template_name:
                template_data = {
                    "customer_name": str(customer_name or "there"),
                    "offer_id": str(offer_id or ""),
                    "label_url": str(label_url or ""),
                    "tracking_number": str(tracking_number or ""),
                    "carrier": str(carrier or "USPS"),
                    "service_level": str(service_level or "Priority Mail"),
                    "reminder_count": str(reminder_count),
                }
                client.send_templated_email(
                    Source=from_email,
                    Destination={"ToAddresses": [recipient]},
                    Template=template_name,
                    TemplateData=json.dumps(template_data),
                )
            else:
                client.send_email(
                    Source=from_email,
                    Destination={"ToAddresses": [recipient]},
                    Message={
                        "Subject": {"Data": f"Reminder: ship your item for offer {offer_id}", "Charset": "UTF-8"},
                        "Body": {
                            "Text": {
                                "Data": (
                                    "This is a reminder to ship your item for an accepted trade.\n\n"
                                    f"Offer: {offer_id}\n"
                                    f"Carrier: {carrier or 'USPS'}\n"
                                    f"Service: {service_level or 'Priority Mail'}\n"
                                    f"Tracking: {tracking_number or 'pending'}\n"
                                    f"Label URL: {label_url}\n"
                                ),
                                "Charset": "UTF-8",
                            }
                        },
                    },
                )
            return "sent_ses"
        except Exception:
            return "failed_ses"

    def _send_via_smtp(recipient: str) -> str:
        host = str(settings.smtp_host or "").strip()
        from_email = str(settings.smtp_from_email or settings.ses_from_email or "").strip()
        if not host or not from_email:
            return "skipped_smtp_not_configured"
        msg = EmailMessage()
        msg["Subject"] = f"Reminder: ship your item for offer {offer_id}"
        msg["From"] = from_email
        msg["To"] = recipient
        msg.set_content(
            "This is a reminder to ship your item for an accepted trade.\n\n"
            f"Offer: {offer_id}\n"
            f"Carrier: {carrier or 'USPS'}\n"
            f"Service: {service_level or 'Priority Mail'}\n"
            f"Tracking: {tracking_number or 'pending'}\n"
            f"Label URL: {label_url}\n"
        )
        try:
            with smtplib.SMTP(host, int(settings.smtp_port), timeout=20) as smtp:
                if settings.smtp_use_tls:
                    smtp.starttls()
                if settings.smtp_username:
                    smtp.login(settings.smtp_username, settings.smtp_password or "")
                smtp.send_message(msg)
            return "sent_smtp"
        except Exception:
            return "failed_smtp"

    recipient = str(to_email or "").strip()
    if not recipient:
        return "skipped_no_recipient"
    provider = str(settings.email_provider or "auto").strip().lower()
    if provider == "ses":
        return _send_via_ses(recipient)
    if provider == "smtp":
        return _send_via_smtp(recipient)
    ses_result = _send_via_ses(recipient)
    if ses_result == "sent_ses":
        return ses_result
    smtp_result = _send_via_smtp(recipient)
    if smtp_result == "sent_smtp":
        return smtp_result
    if ses_result.startswith("failed"):
        return ses_result
    if smtp_result.startswith("failed"):
        return smtp_result
    return "skipped_not_configured"


def _process_shipping_reminders_once(*, settings: Settings) -> None:
    if not settings.shipping_reminder_enabled:
        return
    db = Database(settings.database_url)
    db.initialize()
    now = datetime.now(timezone.utc)
    interval = timedelta(hours=max(1, int(settings.shipping_reminder_interval_hours)))
    pending = db.list_shipments_pending_reminder()
    for shipment in pending:
        try:
            current = dict(shipment)
            if settings.shipping_reminder_auto_track:
                current = _refresh_shipment_tracking_status(db=db, settings=settings, shipment=current)
            status = str(current.get("status") or "").lower()
            if status in {"shipped", "delivered", "cancelled"}:
                continue
            reference_dt = _parse_iso_dt(str(current.get("last_ship_reminder_at") or "")) or _parse_iso_dt(str(current.get("created_at") or ""))
            if reference_dt and (now - reference_dt) < interval:
                continue
            sender = _subject_shipping_snapshot(db, str(current.get("from_subject") or ""), settings)
            email_status = _send_shipping_reminder_email_if_configured(
                settings=settings,
                to_email=sender.get("email"),
                customer_name=sender.get("name"),
                offer_id=str(current.get("offer_id") or ""),
                label_url=str(current.get("label_url") or ""),
                tracking_number=str(current.get("tracking_number") or ""),
                carrier=str(current.get("carrier") or ""),
                service_level=str(current.get("service_level") or ""),
                reminder_count=int(current.get("ship_reminder_count") or 0) + 1,
            )
            if email_status.startswith("sent"):
                db.mark_shipment_reminder_sent(str(current.get("shipment_id") or ""))
            log_json(
                "shipping_reminder_attempt",
                shipment_id=current.get("shipment_id"),
                offer_id=current.get("offer_id"),
                status=current.get("status"),
                email_status=email_status,
            )
        except Exception as exc:
            log_json(
                "shipping_reminder_error",
                shipment_id=shipment.get("shipment_id"),
                error=str(exc),
            )


async def _shipping_reminder_worker() -> None:
    settings = get_settings()
    poll_seconds = max(60, int(settings.shipping_reminder_poll_seconds))
    while True:
        try:
            await asyncio.to_thread(_process_shipping_reminders_once, settings=settings)
        except Exception as exc:
            log_json("shipping_reminder_worker_error", error=str(exc))
        await asyncio.sleep(poll_seconds)


def _repair_listing_media_gallery_once(*, settings: Settings) -> None:
    try:
        db = Database(settings.database_url)
        db.initialize()
        changed = db.migrate_listing_media_urls_to_http()
        if changed:
            log_json("listing_media_gallery_repaired", changed=changed)
    except Exception as exc:
        log_json("listing_media_gallery_repair_failed", error=str(exc))


@app.on_event("startup")
async def _start_shipping_reminder_worker() -> None:
    settings = get_settings()
    await asyncio.to_thread(_repair_listing_media_gallery_once, settings=settings)
    if not settings.shipping_reminder_enabled:
        return
    app.state.shipping_reminder_task = asyncio.create_task(_shipping_reminder_worker())


@app.on_event("shutdown")
async def _stop_shipping_reminder_worker() -> None:
    task = getattr(app.state, "shipping_reminder_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass


def _auto_create_labels_for_accepted_offer_and_notify(*, db: Database, offer: dict, settings: Settings) -> None:
    offer_id = str(offer.get("offer_id") or "")
    if not offer_id:
        return
    from_subject = str(offer.get("from_subject") or "")
    to_subject = str(offer.get("to_subject") or "")
    if not from_subject or not to_subject:
        return

    preexisting_label_urls: dict[tuple[str, str], str] = {}
    for shipment in db.list_shipments_for_offer(offer_id):
        leg = (str(shipment.get("from_subject") or ""), str(shipment.get("to_subject") or ""))
        preexisting_label_urls[leg] = str(shipment.get("label_url") or "").strip()

    for subject in (from_subject, to_subject):
        created_or_updated = _create_or_refresh_trade_shipment_for_subject(
            db=db,
            offer=offer,
            subject=subject,
            settings=settings,
        )
        if not created_or_updated:
            continue
        label_url = str(created_or_updated.get("label_url") or "").strip()
        if not label_url:
            continue
        leg = (
            str(created_or_updated.get("from_subject") or ""),
            str(created_or_updated.get("to_subject") or ""),
        )
        if preexisting_label_urls.get(leg, "") == label_url:
            continue

        sender_subject = leg[0]
        sender_snapshot = _subject_shipping_snapshot(db, sender_subject, settings)
        _send_label_email_if_configured(
            settings=settings,
            to_email=sender_snapshot.get("email"),
            customer_name=sender_snapshot.get("name"),
            offer_id=offer_id,
            label_url=label_url,
            tracking_number=str(created_or_updated.get("tracking_number") or ""),
            carrier=str(created_or_updated.get("carrier") or ""),
            service_level=str(created_or_updated.get("service_level") or ""),
        )
        preexisting_label_urls[leg] = label_url


def _shippo_buy_label(
    *,
    settings: Settings,
    from_addr: dict[str, str | None],
    to_addr: dict[str, str | None],
    parcel_weight_oz: float | None = None,
) -> dict[str, str]:
    key = (settings.shippo_api_key or "").strip()
    if not key:
        return {
            "status": "awaiting_shippo_config",
            "carrier": "USPS",
            "service_level": "Priority Mail",
            "debug": "SHIPPO_API_KEY is not configured",
        }
    if not _address_complete(from_addr) or not _address_complete(to_addr):
        return {
            "status": "awaiting_address",
            "carrier": "USPS",
            "service_level": "Priority Mail",
            "debug": "from/to shipping address is incomplete",
        }
    if not _contact_complete(from_addr) or not _contact_complete(to_addr):
        return {
            "status": "awaiting_contact",
            "carrier": "USPS",
            "service_level": "Priority Mail",
            "debug": "from/to contact info (email + phone) is incomplete",
        }
    base = settings.shippo_api_base_url.rstrip("/")
    headers = {
        "Authorization": f"ShippoToken {key}",
        "Content-Type": "application/json",
    }
    package_weight_oz = float(parcel_weight_oz or settings.shippo_parcel_weight_oz)
    shipment_payload = {
        "address_from": {
            "name": from_addr.get("name"),
            "street1": from_addr.get("line1"),
            "street2": from_addr.get("line2") or "",
            "city": from_addr.get("city"),
            "state": from_addr.get("state"),
            "zip": from_addr.get("postal"),
            "country": from_addr.get("country") or "US",
            "email": from_addr.get("email"),
            "phone": from_addr.get("phone"),
        },
        "address_to": {
            "name": to_addr.get("name"),
            "street1": to_addr.get("line1"),
            "street2": to_addr.get("line2") or "",
            "city": to_addr.get("city"),
            "state": to_addr.get("state"),
            "zip": to_addr.get("postal"),
            "country": to_addr.get("country") or "US",
            "email": to_addr.get("email"),
            "phone": to_addr.get("phone"),
        },
        "parcels": [
            {
                "length": "12",
                "width": "10",
                "height": "6",
                "distance_unit": "in",
                "weight": str(package_weight_oz),
                "mass_unit": "oz",
            }
        ],
        "async": False,
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            ship = client.post(f"{base}/shipments/", json=shipment_payload, headers=headers)
            if ship.status_code >= 400:
                return {
                    "status": "shippo_shipment_error",
                    "carrier": "USPS",
                    "service_level": "Priority Mail",
                    "debug": f"shipment_http_{ship.status_code}: {ship.text[:500]}",
                }
            rates = ship.json().get("rates") or []
            if not isinstance(rates, list) or not rates:
                return {
                    "status": "shippo_no_rates",
                    "carrier": "USPS",
                    "service_level": "Priority Mail",
                    "debug": f"shipment_has_no_rates: {ship.text[:500]}",
                }
            rates_sorted = sorted(rates, key=lambda r: float(r.get("amount") or 1e9))
            chosen = next((r for r in rates_sorted if str(r.get("provider") or "").lower() == "usps"), rates_sorted[0])
            rate_id = str(chosen.get("object_id") or "")
            if not rate_id:
                return {
                    "status": "shippo_no_rate_id",
                    "carrier": "USPS",
                    "service_level": "Priority Mail",
                    "debug": f"selected_rate_has_no_object_id: {json.dumps(chosen)[:500]}",
                }
            txn = client.post(
                f"{base}/transactions/",
                json={"rate": rate_id, "label_file_type": "PDF", "async": False},
                headers=headers,
            )
            if txn.status_code >= 400:
                return {
                    "status": "shippo_transaction_error",
                    "carrier": "USPS",
                    "service_level": str(chosen.get("servicelevel") or "Priority Mail"),
                    "debug": f"transaction_http_{txn.status_code}: {txn.text[:500]}",
                }
            tx = txn.json()
            tx_label_url = (
                tx.get("label_url")
                or tx.get("label_url_pdf")
                or tx.get("label_file")
                or tx.get("label_file_url")
                or ""
            )
            tx_label_url = str(tx_label_url or "").strip()
            tx_status = str(tx.get("status") or "").strip().upper()
            status = "label_created" if tx_label_url and tx_status in {"SUCCESS", "QUEUED", "WAITING"} else "awaiting_label_url"
            return {
                "status": status,
                "carrier": str(chosen.get("provider") or "USPS"),
                "service_level": str((chosen.get("servicelevel") or {}).get("name") if isinstance(chosen.get("servicelevel"), dict) else (chosen.get("servicelevel") or "Priority Mail")),
                "tracking_number": str(tx.get("tracking_number") or ""),
                "label_url": tx_label_url,
                "debug": f"tx_status={tx_status or 'UNKNOWN'}; has_label_url={'yes' if tx_label_url else 'no'}; tx_obj={json.dumps(tx)[:700]}",
            }
    except Exception:
        return {
            "status": "shippo_unavailable",
            "carrier": "USPS",
            "service_level": "Priority Mail",
            "debug": "exception while calling Shippo API",
        }


def _create_trade_shipments_if_missing(*, db: Database, offer: dict, settings: Settings | None = None) -> list[dict]:
    settings = settings or get_settings()
    offer_id = str(offer.get("offer_id") or "")
    if not offer_id:
        return []
    existing = db.list_shipments_for_offer(offer_id)
    if existing:
        if settings:
            refreshed: list[dict] = []
            for s in existing:
                s = _hydrate_shipment_party_fields(db, s)
                if str(s.get("status") or "").lower() == "label_created" and (s.get("label_url") or "").strip():
                    refreshed.append(s)
                    continue
                result = _shippo_buy_label(
                    settings=settings,
                    from_addr={
                        "name": s.get("from_name"),
                        "line1": s.get("from_address_line1"),
                        "line2": s.get("from_address_line2"),
                        "city": s.get("from_city"),
                        "state": s.get("from_state"),
                        "postal": s.get("from_postal_code"),
                        "country": s.get("from_country") or "US",
                        "email": settings.shippo_default_contact_email,
                        "phone": settings.shippo_default_contact_phone,
                    },
                    to_addr={
                        "name": s.get("to_name"),
                        "line1": s.get("to_address_line1"),
                        "line2": s.get("to_address_line2"),
                        "city": s.get("to_city"),
                        "state": s.get("to_state"),
                        "postal": s.get("to_postal_code"),
                        "country": s.get("to_country") or "US",
                        "email": settings.shippo_default_contact_email,
                        "phone": settings.shippo_default_contact_phone,
                    },
                )
                updated = db.update_trade_shipment_label(
                    shipment_id=str(s.get("shipment_id") or ""),
                    carrier=result.get("carrier"),
                    service_level=result.get("service_level"),
                    tracking_number=result.get("tracking_number") or None,
                    label_url=result.get("label_url") or None,
                    status=result.get("status"),
                ) or s
                updated = dict(updated)
                updated["label_debug"] = result.get("debug")
                refreshed.append(updated)
            return refreshed
        return existing
    offered_ids = [x for x in (offer.get("offered_listing_ids") or []) if isinstance(x, str) and x.strip()]
    if not offered_ids and isinstance(offer.get("offered_listing_id"), str):
        offered_ids = [offer["offered_listing_id"]]
    selected_offered_id = str(offer.get("selected_offered_listing_id") or "").strip()
    if selected_offered_id in offered_ids:
        offered_ids = [selected_offered_id]
    if not offered_ids:
        return []
    from_subject = str(offer.get("from_subject") or "")
    to_subject = str(offer.get("to_subject") or "")
    target_listing_id = str(offer.get("target_listing_id") or "")
    sender_profile = _subject_shipping_snapshot(db, from_subject, settings)
    receiver_profile = _subject_shipping_snapshot(db, to_subject, settings)

    created: list[dict] = []
    for offered_id in offered_ids:
        offered_listing = db.get_listing_by_id(offered_id)
        label_result_offer = _shippo_buy_label(
            settings=settings,
            from_addr=sender_profile,
            to_addr=receiver_profile,
            parcel_weight_oz=_estimated_shipping_weight_oz_from_listing(offered_listing, settings),
        )
        tracking_offer = label_result_offer.get("tracking_number") or f"TRD{uuid.uuid4().hex[:12].upper()}"
        shipment_id_offer = str(uuid.uuid4())
        label_url_offer = label_result_offer.get("label_url") or None
        created_offer = db.insert_trade_shipment(
            shipment_id=shipment_id_offer,
            offer_id=offer_id,
            from_subject=from_subject,
            to_subject=to_subject,
            from_listing_id=offered_id,
            to_listing_id=target_listing_id,
            from_name=sender_profile["name"],
            from_address_line1=sender_profile["line1"],
            from_address_line2=sender_profile["line2"],
            from_city=sender_profile["city"],
            from_state=sender_profile["state"],
            from_postal_code=sender_profile["postal"],
            from_country=sender_profile["country"],
            to_name=receiver_profile["name"],
            to_address_line1=receiver_profile["line1"],
            to_address_line2=receiver_profile["line2"],
            to_city=receiver_profile["city"],
            to_state=receiver_profile["state"],
            to_postal_code=receiver_profile["postal"],
            to_country=receiver_profile["country"],
            carrier=label_result_offer.get("carrier") or "USPS",
            service_level=label_result_offer.get("service_level") or "Priority Mail",
            tracking_number=tracking_offer,
            label_url=label_url_offer or "",
            status=label_result_offer.get("status") or "label_created",
        )
        created_offer["label_debug"] = label_result_offer.get("debug")
        created.append(created_offer)
    target_listing = db.get_listing_by_id(target_listing_id)
    label_result_return = _shippo_buy_label(
        settings=settings,
        from_addr=receiver_profile,
        to_addr=sender_profile,
        parcel_weight_oz=_estimated_shipping_weight_oz_from_listing(target_listing, settings),
    )
    tracking_return = label_result_return.get("tracking_number") or f"TRD{uuid.uuid4().hex[:12].upper()}"
    shipment_id_return = str(uuid.uuid4())
    label_url_return = label_result_return.get("label_url") or None
    created_return = db.insert_trade_shipment(
        shipment_id=shipment_id_return,
        offer_id=offer_id,
        from_subject=to_subject,
        to_subject=from_subject,
        from_listing_id=target_listing_id,
        to_listing_id=offered_ids[0],
        from_name=receiver_profile["name"],
        from_address_line1=receiver_profile["line1"],
        from_address_line2=receiver_profile["line2"],
        from_city=receiver_profile["city"],
        from_state=receiver_profile["state"],
        from_postal_code=receiver_profile["postal"],
        from_country=receiver_profile["country"],
        to_name=sender_profile["name"],
        to_address_line1=sender_profile["line1"],
        to_address_line2=sender_profile["line2"],
        to_city=sender_profile["city"],
        to_state=sender_profile["state"],
        to_postal_code=sender_profile["postal"],
        to_country=sender_profile["country"],
        carrier=label_result_return.get("carrier") or "USPS",
        service_level=label_result_return.get("service_level") or "Priority Mail",
        tracking_number=tracking_return,
        label_url=label_url_return or "",
        status=label_result_return.get("status") or "label_created",
    )
    created_return["label_debug"] = label_result_return.get("debug")
    created.append(created_return)
    return created


def _create_or_refresh_trade_shipment_for_subject(
    *,
    db: Database,
    offer: dict,
    subject: str,
    settings: Settings,
    rate_id: str | None = None,
) -> dict | None:
    offer_id = str(offer.get("offer_id") or "")
    if not offer_id:
        return None
    if subject not in {str(offer.get("from_subject") or ""), str(offer.get("to_subject") or "")}:
        return None
    from_subject, to_subject, from_listing_id, to_listing_id = _outbound_leg_for_subject(offer, subject)
    sender_profile = _subject_shipping_snapshot(db, from_subject, settings)
    receiver_profile = _receive_address_snapshot_from_offer(offer=offer, subject=to_subject, db=db, settings=settings)
    receiver_profile["email"] = _subject_shipping_snapshot(db, to_subject, settings).get("email")
    receiver_profile["phone"] = _subject_shipping_snapshot(db, to_subject, settings).get("phone")
    outbound_listing = db.get_listing_by_id(from_listing_id)
    parcel_weight_oz = _estimated_shipping_weight_oz_from_listing(outbound_listing, settings)

    existing_shipments = db.list_shipments_for_offer(offer_id)
    existing_leg = next(
        (
            s for s in existing_shipments
            if str(s.get("from_subject") or "") == from_subject and str(s.get("to_subject") or "") == to_subject
        ),
        None,
    )
    if existing_leg and str(existing_leg.get("status") or "").lower() == "label_created" and str(existing_leg.get("label_url") or "").strip():
        return _hydrate_shipment_party_fields(db, existing_leg)

    quote = _shippo_quote_rate(
        settings=settings,
        from_addr=sender_profile,
        to_addr=receiver_profile,
        parcel_weight_oz=parcel_weight_oz,
    )
    chosen_rate_id = str(rate_id or quote.get("rate_id") or "").strip()
    label_result = _shippo_buy_label_from_rate(settings=settings, rate_id=chosen_rate_id)
    if not chosen_rate_id:
        label_result = {
            "status": quote.get("status") or "shippo_no_rate_id",
            "carrier": quote.get("carrier") or "USPS",
            "service_level": quote.get("service_level") or "Priority Mail",
            "debug": quote.get("debug") or "rate_id unavailable",
        }

    if existing_leg:
        updated = db.update_trade_shipment_label(
            shipment_id=str(existing_leg.get("shipment_id") or ""),
            carrier=label_result.get("carrier"),
            service_level=label_result.get("service_level"),
            tracking_number=label_result.get("tracking_number") or None,
            label_url=label_result.get("label_url") or None,
            status=label_result.get("status"),
        ) or existing_leg
        out = _hydrate_shipment_party_fields(db, updated)
        out["label_debug"] = label_result.get("debug")
        return out

    tracking = label_result.get("tracking_number") or f"TRD{uuid.uuid4().hex[:12].upper()}"
    created = db.insert_trade_shipment(
        shipment_id=str(uuid.uuid4()),
        offer_id=offer_id,
        from_subject=from_subject,
        to_subject=to_subject,
        from_listing_id=from_listing_id,
        to_listing_id=to_listing_id,
        from_name=sender_profile["name"],
        from_address_line1=sender_profile["line1"],
        from_address_line2=sender_profile["line2"],
        from_city=sender_profile["city"],
        from_state=sender_profile["state"],
        from_postal_code=sender_profile["postal"],
        from_country=sender_profile["country"],
        to_name=receiver_profile["name"],
        to_address_line1=receiver_profile["line1"],
        to_address_line2=receiver_profile["line2"],
        to_city=receiver_profile["city"],
        to_state=receiver_profile["state"],
        to_postal_code=receiver_profile["postal"],
        to_country=receiver_profile["country"],
        carrier=label_result.get("carrier") or "USPS",
        service_level=label_result.get("service_level") or "Priority Mail",
        tracking_number=tracking,
        label_url=(label_result.get("label_url") or ""),
        status=label_result.get("status") or "label_created",
    )
    created = _hydrate_shipment_party_fields(db, created)
    created["label_debug"] = label_result.get("debug")
    return created


@app.post("/v1/offers/{offer_id}/shipping-quote", response_model=ShippingQuoteResponse)
def get_shipping_quote(
    offer_id: str,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    offer = db.get_trade_offer_by_id(offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    if principal.subject not in {offer.get("from_subject"), offer.get("to_subject")}:
        raise HTTPException(status_code=403, detail="Forbidden")
    status_norm = str(offer.get("status") or "").lower()
    if status_norm in {"declined", "cancelled"}:
        raise HTTPException(status_code=400, detail="Shipping quote is unavailable for declined or cancelled offers")
    from_subject, to_subject, from_listing_id, _ = _outbound_leg_for_subject(offer, principal.subject)
    from_addr = _subject_shipping_snapshot(db, from_subject, settings)
    to_addr = _receive_address_snapshot_from_offer(offer=offer, subject=to_subject, db=db, settings=settings)
    to_full = _subject_shipping_snapshot(db, to_subject, settings)
    to_addr["email"] = to_full.get("email")
    to_addr["phone"] = to_full.get("phone")
    outbound_listing = db.get_listing_by_id(from_listing_id)
    quote = _shippo_quote_rate(
        settings=settings,
        from_addr=from_addr,
        to_addr=to_addr,
        parcel_weight_oz=_estimated_shipping_weight_oz_from_listing(outbound_listing, settings),
    )
    display_quote = _apply_shippo_flat_rate_quote(settings=settings, quote=quote)
    return ShippingQuoteResponse(
        offer_id=offer_id,
        actor_subject=principal.subject,
        status=display_quote.get("status") or "unknown",
        carrier=display_quote.get("carrier") or "USPS",
        service_level=display_quote.get("service_level") or "Priority Mail",
        amount=display_quote.get("amount"),
        currency=display_quote.get("currency"),
        rate_id=display_quote.get("rate_id"),
        debug=display_quote.get("debug"),
    )


@app.post("/v1/offers/{offer_id}/shipping-labels")
def create_shipping_labels(
    offer_id: str,
    payload: ShippingLabelCreateRequest | None = None,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    payload = payload or ShippingLabelCreateRequest()
    offer = db.get_trade_offer_by_id(offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    if principal.subject not in {offer.get("from_subject"), offer.get("to_subject")}:
        raise HTTPException(status_code=403, detail="Forbidden")
    if str(offer.get("status") or "").lower() != "accepted":
        raise HTTPException(status_code=400, detail="Shipping labels can only be created after both users accept trade")
    if not payload.confirmed:
        raise HTTPException(status_code=400, detail="Shipping cost confirmation is required before creating label")
    if not offer.get("from_receive_address") or not offer.get("to_receive_address"):
        raise HTTPException(status_code=400, detail="Both users must select a receive shipping address before creating labels")
    created_or_updated = _create_or_refresh_trade_shipment_for_subject(
        db=db,
        offer=offer,
        subject=principal.subject,
        settings=settings,
        rate_id=payload.rate_id,
    )
    shipments_all = [_hydrate_shipment_party_fields(db, s) for s in db.list_shipments_for_offer(offer_id)]
    shipments = _visible_shipments_for_subject(shipments=shipments_all, subject=principal.subject)
    email_result = "skipped_no_label"
    if created_or_updated and str(created_or_updated.get("label_url") or "").strip():
        actor_snapshot = _subject_shipping_snapshot(db, principal.subject, settings)
        email_result = _send_label_email_if_configured(
            settings=settings,
            to_email=actor_snapshot.get("email"),
            customer_name=actor_snapshot.get("name"),
            offer_id=offer_id,
            label_url=str(created_or_updated.get("label_url") or ""),
            tracking_number=str(created_or_updated.get("tracking_number") or ""),
            carrier=str(created_or_updated.get("carrier") or ""),
            service_level=str(created_or_updated.get("service_level") or ""),
        )
    return {"offer_id": offer_id, "count": len(shipments), "shipments": shipments, "email_status": email_result}


@app.get("/v1/offers/{offer_id}/shipping-labels")
def list_shipping_labels(
    offer_id: str,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    offer = db.get_trade_offer_by_id(offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    if principal.subject not in {offer.get("from_subject"), offer.get("to_subject")}:
        raise HTTPException(status_code=403, detail="Forbidden")
    shipments_all = []
    for shipment in db.list_shipments_for_offer(offer_id):
        current = shipment
        if settings.shipping_reminder_auto_track:
            current = _refresh_shipment_tracking_status(db=db, settings=settings, shipment=current)
        shipments_all.append(_hydrate_shipment_party_fields(db, current))
    shipments = _visible_shipments_for_subject(shipments=shipments_all, subject=principal.subject)
    return {"offer_id": offer_id, "count": len(shipments), "shipments": shipments}


@app.get("/v1/shipments/{shipment_id}/label")
def get_shipping_label_document(
    shipment_id: str,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    shipment = db.get_trade_shipment_by_id(shipment_id)
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    if principal.subject != shipment.get("from_subject"):
        raise HTTPException(status_code=403, detail="Forbidden")
    if settings.shipping_reminder_auto_track:
        shipment = _refresh_shipment_tracking_status(db=db, settings=settings, shipment=shipment)
    return {
        "shipment_id": shipment.get("shipment_id"),
        "carrier": shipment.get("carrier"),
        "service_level": shipment.get("service_level"),
        "tracking_number": shipment.get("tracking_number"),
        "label_url": shipment.get("label_url"),
        "status": shipment.get("status"),
        "tracking_status": shipment.get("tracking_status"),
        "tracking_status_details": shipment.get("tracking_status_details"),
        "tracking_status_updated_at": shipment.get("tracking_status_updated_at"),
        "tracking_eta": shipment.get("tracking_eta"),
        "tracking_history": shipment.get("tracking_history") or [],
        "from": {
            "name": shipment.get("from_name"),
            "line1": shipment.get("from_address_line1"),
            "line2": shipment.get("from_address_line2"),
            "city": shipment.get("from_city"),
            "state": shipment.get("from_state"),
            "postal_code": shipment.get("from_postal_code"),
            "country": shipment.get("from_country"),
        },
        "to": {
            "name": shipment.get("to_name"),
            "line1": shipment.get("to_address_line1"),
            "line2": shipment.get("to_address_line2"),
            "city": shipment.get("to_city"),
            "state": shipment.get("to_state"),
            "postal_code": shipment.get("to_postal_code"),
            "country": shipment.get("to_country"),
        },
    }


@app.post("/v1/shipments/{shipment_id}/mark-shipped")
def mark_shipping_shipped(
    shipment_id: str,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    shipment = db.get_trade_shipment_by_id(shipment_id)
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    if principal.subject != shipment.get("from_subject"):
        raise HTTPException(status_code=403, detail="Forbidden")
    previous_status = str(shipment.get("tracking_status") or shipment.get("status") or "").strip().lower()
    updated = db.update_trade_shipment_tracking(
        shipment_id=shipment_id,
        status="shipped",
        tracking_status="transit",
        tracking_status_details="Marked shipped by sender",
        tracking_status_updated_at=utc_now_iso(),
        tracking_history=shipment.get("tracking_history") or [],
    )
    if updated:
        _notify_shipment_tracking_update(
            db=db,
            settings=settings,
            shipment=updated,
            previous_status=previous_status,
            next_status=str(updated.get("tracking_status") or updated.get("status") or "").strip().lower(),
        )
    return {"shipment": updated or shipment}


@app.get("/v1/auth/me", response_model=AuthMeResponse)
def auth_me(principal: AuthPrincipal = Depends(require_clerk_user), settings: Settings = Depends(get_settings)) -> AuthMeResponse:
    claims = principal.claims
    email = claims.get("email")
    if not email and isinstance(claims.get("email_addresses"), list) and claims["email_addresses"]:
        first = claims["email_addresses"][0]
        if isinstance(first, dict):
            email = first.get("email_address")
    if not email:
        email = claims.get("primary_email_address")
    return AuthMeResponse(
        provider="clerk",
        user_id=principal.subject,
        email=email,
        username=claims.get("username"),
        first_name=claims.get("first_name"),
        last_name=claims.get("last_name"),
        claims=claims if settings.brand_debug else None,
    )


def _upload_extension(filename: str | None, content_type: str | None) -> str:
    normalized_type = (content_type or "").split(";")[0].strip().lower()
    if normalized_type in {"image/jpeg", "image/jpg"}:
        return ".jpg"
    if normalized_type == "image/png":
        return ".png"
    if normalized_type == "image/webp":
        return ".webp"
    ext = os.path.splitext(filename or "")[1].lower()
    if ext in {".jpg", ".jpeg", ".png", ".webp"}:
        return ".jpg" if ext == ".jpeg" else ext
    return ".jpg"


@app.post("/v1/uploads/images/presign", response_model=PresignImageUploadResponse)
def presign_image_uploads(
    payload: PresignImageUploadRequest,
    settings: Settings = Depends(get_settings),
    principal: AuthPrincipal = Depends(get_request_principal),
    storage: Storage = Depends(get_storage),
) -> PresignImageUploadResponse:
    _ = principal.subject
    item_id = (payload.item_id or "").strip() or f"item-{uuid.uuid4()}"
    if not payload.images:
        raise HTTPException(status_code=400, detail="At least one image is required")
    if len(payload.images) > settings.max_images_per_request:
        raise HTTPException(status_code=400, detail=f"Maximum {settings.max_images_per_request} images")

    slots: list[PresignedImageUploadSlot] = []
    for idx, image in enumerate(payload.images):
        content_type = (image.content_type or "image/jpeg").split(";")[0].strip().lower() or "image/jpeg"
        if not content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="Only image uploads are supported")
        image_uuid = str(uuid.uuid4())
        filename = f"{image_uuid}{_upload_extension(image.filename, content_type)}"
        try:
            upload_url, storage_uri = storage.create_presigned_upload(
                item_id=item_id,
                filename=filename,
                content_type=content_type,
            )
        except NotImplementedError as exc:
            raise HTTPException(status_code=409, detail="Direct uploads are not configured for this environment") from exc
        role_hint = "full_item" if idx == 0 else "close_up"
        slots.append(
            PresignedImageUploadSlot(
                image_id=image_uuid,
                role_hint=role_hint,
                storage_uri=storage_uri,
                image_url=f"/v1/images/{image_uuid}",
                upload_url=upload_url,
                headers={"Content-Type": content_type},
            )
        )

    return PresignImageUploadResponse(item_id=item_id, upload_slots=slots)


@app.post("/v1/uploads/images/confirm", response_model=UploadImagesResponse)
def confirm_presigned_image_uploads(
    payload: ConfirmPresignedImageUploadRequest,
    settings: Settings = Depends(get_settings),
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
    storage: Storage = Depends(get_storage),
) -> UploadImagesResponse:
    _ = principal.subject
    item_id = payload.item_id.strip()
    if not item_id:
        raise HTTPException(status_code=400, detail="item_id is required")
    if not payload.uploaded_images:
        raise HTTPException(status_code=400, detail="At least one uploaded image is required")
    if len(payload.uploaded_images) > settings.max_images_per_request:
        raise HTTPException(status_code=400, detail=f"Maximum {settings.max_images_per_request} images")

    db.insert_item(item_id)
    uploaded_images_out: list[UploadedImageOut] = []
    for idx, image in enumerate(payload.uploaded_images):
        try:
            exists = storage.object_exists(image.storage_uri)
        except NotImplementedError as exc:
            raise HTTPException(status_code=409, detail="Direct uploads are not configured for this environment") from exc
        if not exists:
            raise HTTPException(status_code=400, detail="Uploaded image was not found in storage")
        role_hint = image.role_hint or ("full_item" if idx == 0 else "close_up")
        db.insert_image(
            PersistedImage(
                image_id=image.image_id,
                item_id=item_id,
                storage_uri=image.storage_uri,
                filename=(image.filename or f"{image.image_id}.jpg"),
                role_hint=role_hint,
                content_hash=image.content_hash,
            )
        )
        uploaded_images_out.append(
            UploadedImageOut(
                image_id=image.image_id,
                role_hint=role_hint,
                storage_uri=image.storage_uri,
                image_url=f"/v1/images/{image.image_id}",
            )
        )

    return UploadImagesResponse(item_id=item_id, uploaded_images=uploaded_images_out)


@app.post("/v1/uploads/images", response_model=UploadImagesResponse)
async def upload_images(
    images: Annotated[list[UploadFile], File(...)],
    item_id: Annotated[str | None, Form()] = None,
    settings: Settings = Depends(get_settings),
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
    storage: Storage = Depends(get_storage),
) -> UploadImagesResponse:
    _ = principal.subject
    item_id = (item_id or "").strip() or f"item-{uuid.uuid4()}"
    if not images:
        raise HTTPException(status_code=400, detail="At least one image is required")
    if len(images) > settings.max_images_per_request:
        raise HTTPException(status_code=400, detail=f"Maximum {settings.max_images_per_request} images")

    db.insert_item(item_id)
    file_entries: list[dict[str, object]] = []
    for idx, file in enumerate(images):
        raw = await file.read()
        if raw:
            file_entries.append(
                {
                    "index": idx,
                    "raw": raw,
                    "content_type": file.content_type or "image/jpeg",
                    "filename": file.filename,
                }
            )
    if not file_entries:
        raise HTTPException(status_code=400, detail="No readable images uploaded")

    prepared_entries = await asyncio.gather(
        *[
            asyncio.to_thread(
                _prepare_uploaded_image_for_storage,
                entry["raw"],
                str(entry.get("content_type") or "image/jpeg"),
            )
            for entry in file_entries
        ]
    )

    uploaded_images_out: list[UploadedImageOut] = []
    for entry, prepared in zip(file_entries, prepared_entries):
        raw = entry["raw"]
        if not isinstance(raw, bytes):
            continue
        prepared_raw, prepared_content_type, _prepare_debug = prepared
        idx = int(entry["index"])
        image_uuid = str(uuid.uuid4())
        ext = ".jpg" if prepared_content_type == "image/jpeg" else (os.path.splitext(str(entry.get("filename") or ""))[1] or ".jpg")
        filename = f"{image_uuid}{ext}"
        role_hint = "full_item" if idx == 0 else "close_up"
        storage_uri = storage.save_upload(
            item_id=item_id,
            filename=filename,
            content_type=prepared_content_type,
            data=prepared_raw,
        )
        storage.save_debug_artifact(
            item_id=item_id,
            filename=f"{image_uuid}_original.bin",
            data=raw,
        )
        db.insert_image(
            PersistedImage(
                image_id=image_uuid,
                item_id=item_id,
                storage_uri=storage_uri,
                filename=str(entry.get("filename") or "") or filename,
                role_hint=role_hint,
                content_hash=_image_content_hash(prepared_raw),
            )
        )
        uploaded_images_out.append(
            UploadedImageOut(
                image_id=image_uuid,
                role_hint=role_hint,
                storage_uri=storage_uri,
                image_url=f"/v1/images/{image_uuid}",
            )
        )

    if not uploaded_images_out:
        raise HTTPException(status_code=400, detail="No readable images uploaded")

    return UploadImagesResponse(item_id=item_id, uploaded_images=uploaded_images_out)


async def _run_listing_image_staging_job(
    *,
    listing_id: str,
    owner_subject: str,
    files: list[dict[str, object]],
    settings: Settings,
) -> None:
    if not settings.image_staging_enabled:
        return
    job_db = Database(settings.database_url)
    job_db.initialize()
    job_storage = build_storage(settings)
    current = next((r for r in job_db.list_owner_listings(owner_subject, limit=500) if r["listing_id"] == listing_id), None)
    if current is None:
        log_json("listing_image_staging_missing_listing", listing_id=listing_id, actor=owner_subject)
        return

    source_item_id = str(current.get("source_item_id") or "").strip() or f"item-{listing_id}"
    stage_inputs = [
        entry for entry in files
        if isinstance(entry.get("data"), bytes)
    ][: settings.max_images_per_request]
    if not stage_inputs:
        return

    try:
        log_json("listing_image_staging_started", listing_id=listing_id, actor=owner_subject, image_count=len(stage_inputs))
        staged_entries = await asyncio.gather(
            *[
                asyncio.to_thread(
                    _stage_item_image,
                    entry["data"],
                    str(entry.get("content_type") or "image/jpeg"),
                    settings,
                )
                for entry in stage_inputs
            ]
        )
        staged_urls: list[str] = []
        listed_images: list[dict[str, object]] = []
        for idx, (entry, staged) in enumerate(zip(stage_inputs, staged_entries)):
            staged_raw, staged_content_type, stage_debug = staged
            if not isinstance(stage_debug, dict) or not stage_debug.get("applied"):
                continue
            image_uuid = str(uuid.uuid4())
            ext = ".jpg" if staged_content_type == "image/jpeg" else ".png" if staged_content_type == "image/png" else ".webp" if staged_content_type == "image/webp" else ".jpg"
            filename = f"{image_uuid}{ext}"
            role_hint = "full_item" if idx == 0 else "close_up"
            storage_uri = job_storage.save_upload(
                item_id=source_item_id,
                filename=filename,
                content_type=staged_content_type,
                data=staged_raw,
            )
            job_db.insert_image(
                PersistedImage(
                    image_id=image_uuid,
                    item_id=source_item_id,
                    storage_uri=storage_uri,
                    filename=str(entry.get("filename") or "") or filename,
                    role_hint=role_hint,
                    content_hash=_image_content_hash(staged_raw),
                )
            )
            job_storage.save_debug_artifact(
                item_id=source_item_id,
                filename=f"{image_uuid}_staging.json",
                data=json.dumps(stage_debug, indent=2).encode("utf-8"),
            )
            display_url = f"/v1/images/{image_uuid}"
            staged_urls.append(display_url)
            source_url = entry.get("source_url")
            listed_images.append({
                "p_img": source_url if isinstance(source_url, str) and source_url.strip() else display_url,
                "d_img": display_url,
                "is_hero": idx == 0,
            })

        if not staged_urls:
            log_json("listing_image_staging_no_processed_images", listing_id=listing_id, actor=owner_subject)
            return

        current = next((r for r in job_db.list_owner_listings(owner_subject, limit=500) if r["listing_id"] == listing_id), current)
        job_db.update_listing(
            listing_id=listing_id,
            owner_subject=owner_subject,
            title=str(current.get("title") or "New listing"),
            mode="trade",
            category=str(current.get("category") or "handbag"),
            brand=str(current.get("brand") or "unknown"),
            condition=str(current.get("condition") or "LikeNew"),
            size=current.get("size"),
            estimated_value=float(current.get("estimated_value") or 0),
            city=str(current.get("city") or "Your area"),
            image=staged_urls[0],
            images=listed_images,
            description=str(current.get("description") or ""),
            wants=str(current.get("wants") or "Open to similar-value offers"),
            tags=current.get("tags") if isinstance(current.get("tags"), list) else [],
            source_item_id=source_item_id,
            analysis=current.get("analysis"),
            status=str(current.get("status") or "Review"),
        )
        log_json("listing_image_staging_completed", listing_id=listing_id, actor=owner_subject, image_count=len(staged_urls))
    except Exception as exc:
        log_json("listing_image_staging_error", listing_id=listing_id, actor=owner_subject, error=str(exc))


async def _run_listing_analysis_job(
    *,
    listing_id: str,
    owner_subject: str,
    files: list[dict[str, object]],
    category: str | None,
    item_size: str | None,
    user_condition: str | None,
    item_description: str | None,
    debug: bool,
    settings: Settings,
    valuation_service: ValuationService,
    gpt_item_profiler,
    stage_images_after_analysis: bool = False,
) -> None:
    job_db = Database(settings.database_url)
    job_db.initialize()
    job_storage = build_storage(settings)
    current = next((r for r in job_db.list_owner_listings(owner_subject, limit=500) if r["listing_id"] == listing_id), None)
    if current is None:
        log_json("listing_analysis_job_missing_listing", listing_id=listing_id, actor=owner_subject)
        return
    upload_files: list[UploadFile] = []
    for entry in files:
        data = entry.get("data")
        if not isinstance(data, bytes):
            continue
        content_type = str(entry.get("content_type") or "image/jpeg")
        filename = str(entry.get("filename") or "upload.jpg")
        upload_files.append(
            UploadFile(
                file=BytesIO(data),
                filename=filename,
                size=len(data),
                headers=Headers({"content-type": content_type}),
            )
        )
    if not upload_files:
        log_json("listing_analysis_job_no_files", listing_id=listing_id, actor=owner_subject)
        _mark_listing_analysis_failed(job_db, current, owner_subject)
        return

    try:
        log_json("listing_analysis_job_started", listing_id=listing_id, actor=owner_subject, image_count=len(upload_files))
        payload = await analyze(
            background_tasks=BackgroundTasks(),
            images=upload_files,
            item_id=None,
            category=category,
            item_size=item_size,
            user_condition=user_condition,
            item_description=item_description,
            purchase_year=None,
            debug=debug,
            settings=settings,
            principal=AuthPrincipal(auth_type="analysis_job", subject=owner_subject, claims={"sub": owner_subject}),
            db=job_db,
            storage=job_storage,
            valuation_service=valuation_service,
            gpt_item_profiler=gpt_item_profiler,
        )
        response_payload = payload.model_dump()
        profile = response_payload.get("item_profile") if isinstance(response_payload.get("item_profile"), dict) else {}
        model_identification = profile.get("model_identification") if isinstance(profile.get("model_identification"), dict) else {}
        model_name = str(model_identification.get("name") or "").strip()
        attributes = model_identification.get("attributes")
        attribute_values = [str(a).strip() for a in attributes if isinstance(a, str) and a.strip()] if isinstance(attributes, list) else []
        profile_description = ""
        if model_name and attribute_values:
            profile_description = f"{model_name}. Key details: {', '.join(attribute_values[:6])}."
        elif model_name:
            profile_description = f"Pre-owned {model_name}."
        elif attribute_values:
            profile_description = f"Key details: {', '.join(attribute_values[:6])}."
        brand = str(response_payload.get("brand", {}).get("name") or current.get("brand") or "unknown")
        condition = str(response_payload.get("user_condition") or user_condition or current.get("condition") or "LikeNew")
        resolved_category = str(response_payload.get("category") or current.get("category") or "handbag")
        valuation = response_payload.get("valuation") if isinstance(response_payload.get("valuation"), dict) else {}
        estimated_value = float(valuation.get("estimated_value") or current.get("estimated_value") or 0)
        existing_images = current.get("images") if isinstance(current.get("images"), list) else []
        image_urls = [url for url in existing_images if isinstance(url, str) and url.strip()]
        if not image_urls and isinstance(current.get("image"), str) and current.get("image"):
            image_urls = [str(current["image"])]
        title = _listing_title_from_analysis(
            current.get("title"),
            model_name=model_name,
            profile=profile,
            brand=brand,
            category=resolved_category,
        )
        description = str(current.get("description") or "").strip() or profile_description
        job_db.update_listing(
            listing_id=listing_id,
            owner_subject=owner_subject,
            title=title or "New listing",
            mode="trade",
            category=resolved_category,
            brand=brand,
            condition=condition,
            size=item_size or current.get("size"),
            estimated_value=estimated_value,
            city=str(current.get("city") or "Your area"),
            image=image_urls[0] if image_urls else None,
            images=image_urls,
            description=description,
            wants=str(current.get("wants") or "Open to similar-value offers"),
            tags=[condition, brand, "trade"],
            source_item_id=str(response_payload.get("item_id") or current.get("source_item_id") or ""),
            analysis=response_payload,
            status="Review",
        )
        log_json(
            "listing_analysis_job_completed",
            listing_id=listing_id,
            actor=owner_subject,
            item_id=response_payload.get("item_id"),
            brand=brand,
            category=resolved_category,
            estimated_value=estimated_value,
        )
        if stage_images_after_analysis:
            await _run_listing_image_staging_job(
                listing_id=listing_id,
                owner_subject=owner_subject,
                files=files,
                settings=settings,
            )
        else:
            log_json("listing_image_staging_skipped", listing_id=listing_id, actor=owner_subject, reason="not_new_upload")
    except Exception as exc:
        current = next((r for r in job_db.list_owner_listings(owner_subject, limit=500) if r["listing_id"] == listing_id), None)
        log_json("listing_analysis_job_error", listing_id=listing_id, actor=owner_subject, error=str(exc))
        _mark_listing_analysis_failed(job_db, current, owner_subject)


def _run_listing_analysis_job_threaded(
    *,
    listing_id: str,
    owner_subject: str,
    files: list[dict[str, object]],
    category: str | None,
    item_size: str | None,
    user_condition: str | None,
    item_description: str | None,
    debug: bool,
    settings: Settings,
    valuation_service: ValuationService,
    gpt_item_profiler,
    stage_images_after_analysis: bool = False,
) -> None:
    asyncio.run(
        _run_listing_analysis_job(
            listing_id=listing_id,
            owner_subject=owner_subject,
            files=files,
            category=category,
            item_size=item_size,
            user_condition=user_condition,
            item_description=item_description,
            debug=debug,
            settings=settings,
            valuation_service=valuation_service,
            gpt_item_profiler=gpt_item_profiler,
            stage_images_after_analysis=stage_images_after_analysis,
        )
    )


def _run_listing_analysis_for_existing_listing_job(
    *,
    listing_id: str,
    owner_subject: str,
    category: str | None,
    item_size: str | None,
    user_condition: str | None,
    item_description: str | None,
    debug: bool,
    settings: Settings,
    valuation_service: ValuationService,
    gpt_item_profiler,
    stage_images_after_analysis: bool = False,
) -> None:
    job_db = Database(settings.database_url)
    job_db.initialize()
    current = next((r for r in job_db.list_owner_listings(owner_subject, limit=500) if r["listing_id"] == listing_id), None)
    if current is None:
        log_json("listing_analysis_job_missing_listing", listing_id=listing_id, actor=owner_subject)
        return

    reused_payload = _reuse_recent_analysis_for_listing(
        db=job_db,
        listing_id=listing_id,
        owner_subject=owner_subject,
        current=current,
    )
    if reused_payload:
        log_json("listing_analysis_reused_in_background", listing_id=listing_id, actor=owner_subject)
        return

    files = _collect_listing_analysis_files(db=job_db, settings=settings, listing=current)
    if not files:
        _mark_listing_analysis_failed(job_db, current, owner_subject)
        log_json("listing_analysis_auto_queue_no_files", listing_id=listing_id, actor=owner_subject)
        return

    log_json(
        "listing_analysis_auto_queue_files_collected",
        listing_id=listing_id,
        actor=owner_subject,
        image_count=len(files),
    )
    _run_listing_analysis_job_threaded(
        listing_id=listing_id,
        owner_subject=owner_subject,
        files=files,
        category=category,
        item_size=item_size,
        user_condition=user_condition,
        item_description=item_description,
        debug=debug,
        settings=settings,
        valuation_service=valuation_service,
        gpt_item_profiler=gpt_item_profiler,
        stage_images_after_analysis=stage_images_after_analysis,
    )


@app.post("/v1/listings/{listing_id}/analysis-jobs")
async def queue_listing_analysis(
    listing_id: str,
    background_tasks: BackgroundTasks,
    images: Annotated[list[UploadFile] | None, File()] = None,
    image_urls_json: Annotated[str | None, Form()] = None,
    category: Annotated[str | None, Form()] = None,
    item_size: Annotated[str | None, Form()] = None,
    user_condition: Annotated[str | None, Form()] = None,
    item_description: Annotated[str | None, Form()] = None,
    debug: Annotated[bool, Form()] = False,
    settings: Settings = Depends(get_settings),
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
    valuation_service: ValuationService = Depends(get_valuation_service),
    gpt_item_profiler=Depends(get_gpt_item_profiler),
) -> dict[str, str]:
    current = next((r for r in db.list_owner_listings(principal.subject, limit=500) if r["listing_id"] == listing_id), None)
    if current is None:
        raise HTTPException(status_code=404, detail="listing not found")

    files: list[dict[str, object]] = []
    uploaded_file_count = 0
    for file in images or []:
        raw = await file.read()
        if raw:
            uploaded_file_count += 1
            files.append({
                "filename": file.filename or "upload.jpg",
                "content_type": file.content_type or "image/jpeg",
                "data": raw,
            })
    image_urls: list[str] = []
    if image_urls_json:
        try:
            parsed_urls = json.loads(image_urls_json)
            if isinstance(parsed_urls, list):
                image_urls = [str(url).strip() for url in parsed_urls if str(url).strip()]
        except Exception:
            raise HTTPException(status_code=400, detail="image_urls_json must be a JSON array")
    source_item_id = str(current.get("source_item_id") or "").strip() or None
    for idx, image_url in enumerate(image_urls):
        try:
            resolved = _image_file_from_listing_url(
                db=db,
                settings=settings,
                url=image_url,
                index=idx,
                source_item_id=source_item_id,
            )
        except Exception:
            resolved = None
        if resolved:
            files.append(resolved)
    deduped_files: list[dict[str, object]] = []
    seen_signatures: set[tuple[str, int]] = set()
    for entry in files:
        data = entry.get("data")
        if not isinstance(data, bytes):
            continue
        signature = (str(entry.get("filename") or ""), len(data))
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        deduped_files.append(entry)
    files = deduped_files[: settings.max_images_per_request]
    if not files:
        _mark_listing_analysis_failed(db, current, principal.subject)
        log_json("listing_analysis_queue_no_files", listing_id=listing_id, actor=principal.subject)
        raise HTTPException(status_code=400, detail="No readable images uploaded")

    background_tasks.add_task(
        _run_listing_analysis_job_threaded,
        listing_id=listing_id,
        owner_subject=principal.subject,
        files=files,
        category=category,
        item_size=item_size,
        user_condition=user_condition,
        item_description=item_description,
        debug=debug,
        settings=settings,
        valuation_service=valuation_service,
        gpt_item_profiler=gpt_item_profiler,
        stage_images_after_analysis=uploaded_file_count > 0,
    )
    return {"status": "queued"}


@app.post("/v1/analyze", response_model=AnalyzeResponse)
async def analyze(
    background_tasks: BackgroundTasks,
    images: Annotated[list[UploadFile], File(...)],
    item_id: Annotated[str | None, Form()] = None,
    category: Annotated[str | None, Form()] = None,
    item_size: Annotated[str | None, Form()] = None,
    user_condition: Annotated[str | None, Form()] = None,
    item_description: Annotated[str | None, Form()] = None,
    purchase_year: Annotated[int | None, Form()] = None,
    debug: Annotated[bool, Form()] = False,
    settings: Settings = Depends(get_settings),
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
    storage: Storage = Depends(get_storage),
    valuation_service: ValuationService = Depends(get_valuation_service),
    gpt_item_profiler=Depends(get_gpt_item_profiler),
) -> AnalyzeResponse:
    item_id = (item_id or "").strip() or f"item-{uuid.uuid4()}"
    category = normalize_category(category)
    item_size = normalize_item_size(item_size)
    user_condition_grade = normalize_condition_grade(user_condition)
    if purchase_year is not None and (purchase_year < 1980 or purchase_year > 2100):
        raise HTTPException(status_code=400, detail="purchase_year out of expected range")
    if not images:
        raise HTTPException(status_code=400, detail="At least one image is required")
    if len(images) > settings.max_images_per_request:
        raise HTTPException(status_code=400, detail=f"Maximum {settings.max_images_per_request} images")

    t0 = time.perf_counter()
    db.insert_item(item_id)

    image_inputs: list[ImageInput] = []
    uploaded_refs: list[dict] = []
    uploaded_images_out: list[UploadedImageOut] = []
    for idx, file in enumerate(images):
        raw = await file.read()
        if not raw:
            continue
        prepared_raw, prepared_content_type, stage_debug = _prepare_uploaded_image_for_storage(raw, file.content_type or "image/jpeg")
        image_uuid = str(uuid.uuid4())
        ext = ".jpg" if prepared_content_type == "image/jpeg" else (os.path.splitext(file.filename or "")[1] or ".jpg")
        filename = f"{image_uuid}{ext}"
        role_hint = "full_item" if idx == 0 else "close_up"
        storage_uri = storage.save_upload(
            item_id=item_id,
            filename=filename,
            content_type=prepared_content_type,
            data=prepared_raw,
        )
        storage.save_debug_artifact(
            item_id=item_id,
            filename=f"{image_uuid}_original.bin",
            data=raw,
        )
        db.insert_image(
            PersistedImage(
                image_id=image_uuid,
                item_id=item_id,
                storage_uri=storage_uri,
                filename=file.filename or filename,
                role_hint=role_hint,
                content_hash=_image_content_hash(prepared_raw),
            )
        )
        image_inputs.append(
            ImageInput(
                image_id=image_uuid,
                filename=file.filename or filename,
                content_type=prepared_content_type,
                bytes_data=prepared_raw,
                role_hint=role_hint,
            )
        )
        uploaded_refs.append(
            {
                "image_id": image_uuid,
                "storage_uri": storage_uri,
                "role_hint": role_hint,
                "staging": stage_debug,
                "analysis_source": "original_upload",
            }
        )
        uploaded_images_out.append(
            UploadedImageOut(
                image_id=image_uuid,
                role_hint=role_hint,
                storage_uri=storage_uri,
                image_url=f"/v1/images/{image_uuid}",
            )
        )

    if not image_inputs:
        raise HTTPException(status_code=400, detail="No readable images uploaded")

    requested_photos: list[str] = []
    brand_debug: dict[str, object] = {"source": "gemini_only"}
    cond_debug: dict[str, object] = {"source": "gemini_only"}
    category_out = category or "clothes"
    condition_out = ConditionOut(
        grade=user_condition_grade or "LikeNew",
        confidence=1.0 if user_condition_grade is not None else 0.35,
        issues=[],
    )
    warnings = []
    if user_condition_grade is None:
        warnings.append("Condition set to LikeNew by default. Select condition to improve pricing accuracy.")
    valuation_condition_grade = user_condition_grade or condition_out.grade
    valuation_condition_confidence = condition_out.confidence
    t_brand = 0.0
    t_cond = 0.0

    valuation_payload = None
    valuation_debug = None
    valuation_request: ValuationRequest | None = None
    item_profile_payload = None
    item_profile_debug: dict[str, object] = {
        "enabled": settings.gpt_item_profile_enabled,
        "called": False,
        "error": None,
    }
    sync_valuation_service = valuation_service
    valuation_providers = [p.strip() for p in settings.valuation_providers.split(",") if p.strip()]
    firecrawl_agent_enabled = "firecrawl_agent" in valuation_providers
    sync_providers = [p for p in valuation_providers if p != "firecrawl_agent"]
    if firecrawl_agent_enabled and sync_providers:
        sync_valuation_service = build_valuation_service(settings, sync_providers)
    t_profile_0 = time.perf_counter()
    if settings.gpt_item_profile_enabled:
        profile_result = await asyncio.to_thread(
            gpt_item_profiler.profile_item,
            images=image_inputs,
            brand_name="unknown",
            category=category_out,
            item_size=item_size,
            condition_grade=valuation_condition_grade,
            condition_source="user_input" if user_condition_grade is not None else "model",
            item_description=item_description,
        )
        item_profile_debug = {
            "enabled": profile_result.enabled,
            "called": profile_result.called,
            "error": profile_result.error,
        }
        item_profile_payload = profile_result.profile
        if isinstance(item_profile_payload, dict):
            grounding_metadata = item_profile_payload.pop("_grounding_metadata", None)
            if grounding_metadata is not None:
                item_profile_debug["groundingMetadata"] = grounding_metadata
            workflow_debug = item_profile_payload.pop("_workflow", None)
            if workflow_debug is not None:
                item_profile_debug["workflow"] = workflow_debug
                apply_gemini_grounded_retail_reference(item_profile_payload, workflow_debug, item_profile_debug)
        inferred_profile_category = infer_category_from_item_profile(item_profile_payload)
        if (
            inferred_profile_category
            and inferred_profile_category in VALID_CATEGORIES
            and inferred_profile_category != category_out
        ):
            item_profile_debug["category_reconciled"] = {
                "from": category_out,
                "to": inferred_profile_category,
                "source": "gpt_item_profile",
            }
            category_out = inferred_profile_category
    else:
        raise HTTPException(status_code=503, detail="Gemini item profiler is required and currently disabled")
    t_profile = time.perf_counter() - t_profile_0

    inferred_profile_brand, inferred_profile_brand_conf, inferred_brand_source = infer_brand_from_item_profile(item_profile_payload)
    if inferred_profile_brand:
        brand_out = BrandOut(
            name=inferred_profile_brand,
            confidence=inferred_profile_brand_conf if inferred_profile_brand_conf is not None else 0.5,
            evidence=inferred_brand_source or "gpt_item_profile",
        )
        item_profile_debug["brand_reconciled"] = {
            "from": "unknown",
            "to": brand_out.name,
            "source": inferred_brand_source or "gpt_item_profile",
        }
    else:
        brand_out = BrandOut(name="unknown", confidence=0.0, evidence="insufficient_evidence")

    auth_doc_warning = build_auth_doc_warning(item_profile_payload, image_inputs, brand_name=brand_out.name)
    if auth_doc_warning and auth_doc_warning not in warnings:
        warnings.append(auth_doc_warning)
        requested_photos.append("authenticity_receipt")
        requested_photos = list(dict.fromkeys(requested_photos))

    if settings.valuation_enabled and brand_out.name != "unknown":
        valuation_payload = valuation_from_gpt_item_profile(
            item_profile_payload,
            default_currency=settings.valuation_currency,
            condition_grade=valuation_condition_grade,
        )
        if debug and valuation_payload is not None:
            valuation_debug = {
                "pricing_source": "gpt_primary",
                "pricing_fallback_used": False,
            }
        if valuation_payload is None and settings.valuation_comps_enabled:
            valuation_request = ValuationRequest(
                item_id=item_id,
                brand=brand_out.name,
                brand_confidence=brand_out.confidence,
                category=category_out,
                condition_grade=valuation_condition_grade,
                condition_confidence=valuation_condition_confidence,
                issues=[issue.model_dump() for issue in condition_out.issues],
                item_description=item_description,
                size=item_size,
                purchase_year=purchase_year,
            )
            valuation_result = await asyncio.to_thread(sync_valuation_service.evaluate, valuation_request, debug=debug)
            valuation_payload = valuation_service.serialize(valuation_result)
            valuation_debug = valuation_payload.pop("_debug", None)
            if debug:
                valuation_debug = valuation_debug or {}
                valuation_debug["pricing_source"] = "crawler_fallback"
                valuation_debug["pricing_fallback_used"] = True
                if firecrawl_agent_enabled:
                    valuation_debug["agent_enrichment"] = {
                        "status": "queued",
                        "provider": "firecrawl_agent",
                    }
        elif valuation_payload is None and debug:
            valuation_debug = {
                "pricing_source": "none",
                "pricing_fallback_used": False,
                "comps_fallback_skipped": True,
                "reason": "valuation_comps_disabled",
            }
        if debug:
            valuation_debug = valuation_debug or {}
            valuation_debug["condition_source"] = "user_input" if user_condition_grade is not None else "model"
            valuation_debug["condition_grade_used"] = valuation_condition_grade

    debug_payload = None
    if debug:
        debug_payload = {
            "uploads": uploaded_refs,
            "brand": brand_debug or {},
            "condition": cond_debug or {},
            "thresholds": {
                "BRAND_ACCEPT_SCORE": settings.brand_accept_score,
                "BRAND_ACCEPT_SCORE_LOW": settings.brand_accept_score_low,
                "BRAND_GAP_MIN": settings.brand_gap_min,
            },
            "valuation": valuation_debug or {},
            "enrichment": {"gpt_item_profile": item_profile_debug},
            "input_hints": {
                "user_condition": user_condition_grade,
                "item_size": item_size,
                "item_description": item_description,
                "purchase_year": purchase_year,
            },
        }
        storage.save_debug_artifact(
            item_id=item_id,
            filename=f"{uuid.uuid4()}_debug.json",
            data=json.dumps(debug_payload, indent=2).encode("utf-8"),
        )

    response = AnalyzeResponse(
        item_id=item_id,
        category=category_out,  # type: ignore[arg-type]
        brand=brand_out,
        condition=condition_out,
        user_condition=user_condition_grade,
        valuation=valuation_payload,
        item_profile=item_profile_payload,
        requested_photos=requested_photos,
        warnings=warnings,
        uploaded_images=uploaded_images_out,
        debug=debug_payload,
    )

    analysis_id = str(uuid.uuid4())
    response_payload = response.model_dump()
    db.insert_analysis(analysis_id, item_id, response_payload)
    if user_condition_grade is not None:
        db.insert_condition_feedback(
            str(uuid.uuid4()),
            item_id,
            user_condition_grade,
            condition_out.grade,
            warnings,
            response_payload,
        )
    if (
        settings.valuation_enabled
        and firecrawl_agent_enabled
        and brand_out.name != "unknown"
        and valuation_payload is not None
        and valuation_request is not None
    ):
        background_tasks.add_task(
            enrich_analysis_with_firecrawl_agent,
            analysis_id=analysis_id,
            response_payload=response_payload,
            valuation_request=valuation_request,
            settings=settings,
            db=db,
        )
    total = time.perf_counter() - t0
    log_json(
        "analysis_complete",
        item_id=item_id,
        auth_type=principal.auth_type,
        actor=principal.subject,
        user_condition=user_condition_grade,
        timings={
            "total_ms": round(total * 1000, 2),
            "brand_ms": round(t_brand * 1000, 2),
            "condition_ms": round(t_cond * 1000, 2),
            "gpt_profile_ms": round(t_profile * 1000, 2),
        },
        category=response.category,
        brand=response.brand.model_dump(),
        condition={"grade": response.condition.grade, "confidence": response.condition.confidence},
        valuation=response.valuation,
        item_profile_included=bool(response.item_profile),
        requested_photos=response.requested_photos,
        warnings=warnings,
        thresholds={
            "accept": settings.brand_accept_score,
            "accept_low": settings.brand_accept_score_low,
            "gap_min": settings.brand_gap_min,
        },
    )
    return response
