from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from brand.types import ImageInput
from condition.service import ConditionAnalyzer
from valuation import ValuationConfig, ValuationService
from valuation.types import ValuationRequest

from .auth import AuthPrincipal, get_request_principal, require_clerk_user
from .db import Database, PersistedImage
from .deps import (
    get_brand_analyzer,
    get_condition_analyzer,
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
    ConditionGrade,
    ConditionOut,
    HealthResponse,
    ListingCreateRequest,
    ListingResponse,
    VersionResponse,
)
from .settings import Settings
from .storage import Storage


app = FastAPI(title="ValueAI Fashion Analyzer", version="0.1.0")
_cors_origins = [o.strip() for o in get_settings().cors_allow_origins.split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
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

VALID_CATEGORIES = {"clothes", "shoes", "handbag"}
VALID_CONDITION_GRADES = {"new": "New", "likenew": "LikeNew", "good": "Good", "fair": "Fair", "poor": "Poor"}
CONDITION_SEVERITY_RANK = {"New": 5, "LikeNew": 4, "Good": 3, "Fair": 2, "Poor": 1}


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


def valuation_from_gpt_item_profile(
    item_profile: dict[str, object] | None,
    *,
    default_currency: str,
) -> dict[str, object] | None:
    if not isinstance(item_profile, dict):
        return None

    resale = item_profile.get("resale_price_estimate")
    retail = item_profile.get("retail_price_estimate")
    if not isinstance(resale, dict):
        return None

    estimated_value = _coerce_positive_float(resale.get("estimated_price"))
    if estimated_value is None:
        return None

    retail_reference = _coerce_positive_float(retail.get("estimated_price")) if isinstance(retail, dict) else None
    confidence = resale.get("confidence")
    try:
        confidence_01 = max(0.0, min(float(confidence), 1.0))
    except Exception:
        confidence_01 = 0.5
    currency = resale.get("currency") if isinstance(resale.get("currency"), str) else default_currency

    return {
        "estimated_value": round(estimated_value, 2),
        "currency": currency,
        "range_low": None,
        "range_high": None,
        "confidence": round(confidence_01, 3),
        "basis": "gpt_resale_estimate_primary",
        "comps_summary": {"count": 1, "source_breakdown": {"gpt_item_profile": 1}},
        "resale_market_value": round(estimated_value, 2),
        "retail_reference_value": round(retail_reference, 2) if retail_reference is not None else None,
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
    norm = value.strip().replace(" ", "").casefold()
    if not norm:
        return None
    if norm not in VALID_CONDITION_GRADES:
        raise HTTPException(status_code=400, detail="user_condition must be New|LikeNew|Good|Fair|Poor")
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
    if user_condition in {"New", "LikeNew", "Good"} and model_condition in {"Fair", "Poor"}:
        return [
            f"User marked item as {user_condition}, but model assessment suggests {model_condition}. Review wear/damage before listing."
        ]
    return []


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
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="UI not available")
    return FileResponse(index_path)


@app.get("/v1/version", response_model=VersionResponse)
def version(settings: Settings = Depends(get_settings)) -> VersionResponse:
    return VersionResponse(version=settings.version)


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
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
):
    listing_id = str(uuid.uuid4())
    owner_name = None
    if principal.auth_type == "clerk":
        owner_name = (
            principal.claims.get("name")
            or principal.claims.get("username")
            or principal.claims.get("email")
        )
    created_at = db.insert_listing(
        listing_id=listing_id,
        owner_subject=principal.subject,
        owner_name=owner_name,
        title=payload.title,
        mode=payload.mode,
        category=payload.category,
        brand=payload.brand,
        condition=payload.condition,
        estimated_value=payload.estimated_value,
        city=payload.city,
        image=payload.image,
        wants=payload.wants,
        tags=payload.tags,
        source_item_id=payload.source_item_id,
        analysis=payload.analysis,
    )
    return ListingResponse(
        listing_id=listing_id,
        owner_subject=principal.subject,
        owner_name=owner_name,
        created_at=created_at,
        **payload.model_dump(),
    )


@app.get("/v1/listings")
def list_recent_listings(
    limit: int = 50,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
):
    safe_limit = max(1, min(limit, 100))
    records = db.list_recent_listings(limit=safe_limit)
    return {
        "count": len(records),
        "items": records,
        "actor": {"auth_type": principal.auth_type, "subject": principal.subject},
    }


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
    brand_analyzer=Depends(get_brand_analyzer),
    condition_analyzer: ConditionAnalyzer = Depends(get_condition_analyzer),
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
    for idx, file in enumerate(images):
        raw = await file.read()
        if not raw:
            continue
        image_uuid = str(uuid.uuid4())
        ext = os.path.splitext(file.filename or "")[1] or ".jpg"
        filename = f"{image_uuid}{ext}"
        role_hint = "full_item" if idx == 0 else "close_up"
        storage_uri = storage.save_upload(
            item_id=item_id,
            filename=filename,
            content_type=file.content_type or "image/jpeg",
            data=raw,
        )
        db.insert_image(
            PersistedImage(
                image_id=image_uuid,
                item_id=item_id,
                storage_uri=storage_uri,
                filename=file.filename or filename,
                role_hint=role_hint,
            )
        )
        image_inputs.append(
            ImageInput(
                image_id=image_uuid,
                filename=file.filename or filename,
                content_type=file.content_type or "image/jpeg",
                bytes_data=raw,
                role_hint=role_hint,
            )
        )
        uploaded_refs.append({"image_id": image_uuid, "storage_uri": storage_uri, "role_hint": role_hint})

    if not image_inputs:
        raise HTTPException(status_code=400, detail="No readable images uploaded")

    t_brand_0 = time.perf_counter()
    brand_result = brand_analyzer.analyze(image_inputs, debug=debug)
    t_brand = time.perf_counter() - t_brand_0

    t_cond_0 = time.perf_counter()
    condition_result = condition_analyzer.analyze(
        primary_image=image_inputs[0].bytes_data,
        category_hint=category,
        debug=debug,
    )
    t_cond = time.perf_counter() - t_cond_0

    requested_photos = list(dict.fromkeys(brand_result.pop("_requested_photos", [])))
    brand_debug = brand_result.pop("_debug", None)
    brand_out = BrandOut(**{k: brand_result[k] for k in ("name", "confidence", "evidence")})

    category_out = category or condition_result.category
    cond_payload = ConditionAnalyzer.serialize(condition_result)
    cond_debug = cond_payload.pop("_debug", None)
    condition_out = ConditionOut(**cond_payload)
    warnings = build_condition_warnings(user_condition_grade, condition_out.grade)
    valuation_condition_grade = user_condition_grade or condition_out.grade
    valuation_condition_confidence = 1.0 if user_condition_grade is not None else condition_out.confidence

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
    if settings.gpt_item_profile_enabled and brand_out.name != "unknown":
        profile_result = gpt_item_profiler.profile_item(
            images=image_inputs,
            brand_name=brand_out.name,
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
    t_profile = time.perf_counter() - t_profile_0

    if settings.valuation_enabled and brand_out.name != "unknown":
        valuation_payload = valuation_from_gpt_item_profile(
            item_profile_payload,
            default_currency=settings.valuation_currency,
        )
        if debug and valuation_payload is not None:
            valuation_debug = {
                "pricing_source": "gpt_primary",
                "pricing_fallback_used": False,
            }
        if valuation_payload is None:
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
            valuation_result = sync_valuation_service.evaluate(valuation_request, debug=debug)
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
