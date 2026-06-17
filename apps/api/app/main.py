from __future__ import annotations

import json
import os
import re
import smtplib
import time
import uuid
from io import BytesIO
from pathlib import Path
from email.message import EmailMessage
from typing import Annotated
from urllib.parse import urlparse

import boto3
import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageFilter, ImageOps

from brand.types import ImageInput
from valuation import ValuationConfig, ValuationService
from valuation.types import ValuationRequest

from .auth import AuthPrincipal, get_request_principal, require_clerk_user
from .db import Database, PersistedImage
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
    StripeSetupCheckoutRequest,
    StripeSetupCheckoutResponse,
    StripeAttachPaymentMethodRequest,
    StripeSetupIntentResponse,
    UploadedImageOut,
    UserProfileQuizResponse,
    UserProfileQuizUpdateRequest,
    VersionResponse,
)
from .settings import Settings
from .storage import Storage


app = FastAPI(title="ValueAI Fashion Analyzer", version="0.1.0")
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
VALID_CONDITION_GRADES = {"new": "New", "likenew": "LikeNew", "good": "Good", "fair": "Fair", "poor": "Poor"}
CONDITION_SEVERITY_RANK = {"New": 5, "LikeNew": 4, "Good": 3, "Fair": 2, "Poor": 1}


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


def _normalize_listing_media_for_storage(
    *,
    db: Database,
    image: str | None,
    images: list[str] | None,
    source_item_id: str | None,
) -> tuple[str | None, list[str]]:
    def resolve(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        s = value.strip()
        if not s or s.startswith("blob:") or s.startswith("data:"):
            return None
        if s.startswith("http://") or s.startswith("https://") or s.startswith("/"):
            return s
        if s.startswith("s3://"):
            image_id = db.get_image_id_by_storage_uri(s)
            if image_id:
                return f"/v1/images/{image_id}"
            return None
        return None

    normalized_images: list[str] = []
    if isinstance(images, list):
        for entry in images:
            url = resolve(entry)
            if url:
                normalized_images.append(url)

    normalized_image = resolve(image)
    if normalized_image and normalized_image not in normalized_images:
        normalized_images.insert(0, normalized_image)

    if not normalized_image and normalized_images:
        normalized_image = normalized_images[0]

    return normalized_image, normalized_images


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


def _stage_item_image(raw: bytes, content_type: str, settings: Settings) -> tuple[bytes, str, dict[str, object]]:
    if not settings.image_staging_enabled:
        return raw, content_type, {"applied": False, "reason": "disabled"}
    try:
        with Image.open(BytesIO(raw)) as src:
            src_rgba = src.convert("RGBA")
    except Exception:
        return raw, content_type, {"applied": False, "reason": "open_failed"}

    # 1) Try Gemini image-edit first (white background), fallback to local rembg pipeline.
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
            base_img = Image.open(BytesIO(raw)).convert("RGB")
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
                    "Keep original lighting and realistic shadows."
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
                        "gemini_edit": {**gemini_stage_debug, "reason": "success"},
                    }
            gemini_stage_debug["reason"] = "no_generated_images"
            gemini_stage_debug["status_code"] = 200
        except Exception as exc:
            gemini_stage_debug["reason"] = "exception"
            gemini_stage_debug["error"] = str(exc)[:500]

    fg = src_rgba
    used_rembg = False
    rembg_effective = False
    if settings.condition_rembg_enabled:
        try:
            from rembg import remove  # type: ignore

            removed = remove(
                raw,
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
                mask_bytes = remove(raw, only_mask=True)
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

        shadow = Image.new("RGBA", (nw, max(8, int(nh * 0.1))), (0, 0, 0, 85))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=8))
        sx = (w - nw) // 2
        sy = min(h - shadow.height - 6, (h - nh) // 2 + nh - int(shadow.height * 0.4))
        bg.alpha_composite(shadow, (sx, sy))

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
        if target == "new":
            if "original retail" in lbl:
                return 100
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
    if estimated_value is None:
        estimated_value, range_low, range_high, pricing_row_label = _select_breakdown_row(
            resale_breakdown,
            condition_grade=condition_grade,
        )
    if estimated_value is None:
        return None

    retail_reference = _coerce_positive_float(retail.get("estimated_price")) if isinstance(retail, dict) else None
    confidence = resale.get("confidence") if isinstance(resale, dict) else None
    try:
        confidence_01 = max(0.0, min(float(confidence), 1.0))
    except Exception:
        confidence_01 = 0.5
    currency = resale.get("currency") if isinstance(resale, dict) and isinstance(resale.get("currency"), str) else default_currency

    return {
        "estimated_value": round(estimated_value, 2),
        "currency": currency,
        "range_low": round(range_low, 2) if isinstance(range_low, (int, float)) else None,
        "range_high": round(range_high, 2) if isinstance(range_high, (int, float)) else None,
        "confidence": round(confidence_01, 3),
        "basis": "gpt_resale_estimate_primary" if pricing_row_label == "resale_price_estimate" else "gpt_resale_breakdown_condition_selected",
        "comps_summary": {"count": 1, "source_breakdown": {"gpt_item_profile": 1}},
        "resale_market_value": round(estimated_value, 2),
        "retail_reference_value": round(retail_reference, 2) if retail_reference is not None else None,
        "selected_breakdown_label": pricing_row_label if pricing_row_label != "resale_price_estimate" else None,
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
            gender=None,
            tops_size=None,
            dresses_size=None,
            bottoms_size=None,
            shoes_size=None,
            category_preferences=[],
            shipping_full_name=None,
            shipping_address_line1=None,
            shipping_address_line2=None,
            shipping_city=None,
            shipping_state=None,
            shipping_postal_code=None,
            shipping_country=None,
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
        gender=payload.gender,
        tops_size=payload.tops_size,
        dresses_size=payload.dresses_size,
        bottoms_size=payload.bottoms_size,
        shoes_size=payload.shoes_size,
        category_preferences=payload.category_preferences,
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
        shipping_email=((existing.get("shipping_email") or "").strip() or None),
        shipping_phone=((existing.get("shipping_phone") or "").strip() or None),
        shipping_addresses=shipping_addresses_payload,
        subscription_plan=payload.subscription_plan,
        subscription_billing_cycle=payload.subscription_billing_cycle,
        subscription_status=payload.subscription_status,
        subscription_renewal_date=payload.subscription_renewal_date,
        payment_methods=payload.payment_methods,
    )
    return UserProfileQuizResponse(**saved)


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
                    "success_url": payload.success_url,
                    "cancel_url": payload.cancel_url,
                },
                auth=(secret_key, ""),
            )
            if session_resp.status_code >= 400:
                raise HTTPException(status_code=502, detail="Stripe checkout session creation failed")
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


@app.get("/v1/usps/address-suggest")
def usps_address_suggest(
    q: str = Query(default="", min_length=0, max_length=120),
    city: str | None = Query(default=None, max_length=80),
    state: str | None = Query(default=None, max_length=2),
    postal_code: str | None = Query(default=None, max_length=10),
    _principal: AuthPrincipal = Depends(get_request_principal),
    settings: Settings = Depends(get_settings),
):
    token = (settings.usps_bearer_token or "").strip()
    if not token:
        return {"suggestions": []}
    street = (q or "").strip()
    if len(street) < 5:
        return {"suggestions": []}
    normalized_state = (state or "").strip().upper()
    if len(normalized_state) != 2:
        return {"suggestions": []}
    params: dict[str, str] = {
        "streetAddress": street,
        "state": normalized_state,
    }
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
    city_name = str(address.get("cityAbbreviation") or address.get("city") or "").strip()
    state_code = str(address.get("state") or normalized_state).strip().upper()
    zip_code = str(address.get("ZIPCode") or "").strip()
    plus4 = str(address.get("ZIPPlus4") or "").strip()
    postal = zip_code if not plus4 else f"{zip_code}-{plus4}"
    formatted = ", ".join([x for x in [street_line, city_name, state_code, postal] if x])
    suggestion = {
        "street_address": street_line,
        "city": city_name,
        "state": state_code,
        "postal_code": postal,
        "formatted": formatted,
    }
    if not street_line:
        return {"suggestions": []}
    return {"suggestions": [suggestion]}


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

    signed = _presign_s3_uri(storage_uri, settings)
    if signed:
        return RedirectResponse(signed, status_code=307)

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
    normalized_image, normalized_images = _normalize_listing_media_for_storage(
        db=db,
        image=payload.image,
        images=payload.images,
        source_item_id=payload.source_item_id,
    )
    listing_id = str(uuid.uuid4())
    owner_name = None
    if principal.auth_type == "clerk":
        owner_name = (
            principal.claims.get("name")
            or " ".join(
                p for p in [
                    principal.claims.get("given_name"),
                    principal.claims.get("family_name"),
                ] if isinstance(p, str) and p.strip()
            )
            or principal.claims.get("username")
            or principal.claims.get("email")
        )
        if isinstance(owner_name, str):
            owner_name = owner_name.strip()
    if not owner_name:
        owner_name = principal.subject
    created_at = db.insert_listing(
        listing_id=listing_id,
        owner_subject=principal.subject,
        owner_name=owner_name,
        title=payload.title,
        mode=payload.mode,
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
    mine: bool = False,
    include_matches: bool = False,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    def _to_http_image_url(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        s = value.strip()
        if not s or s.startswith("blob:"):
            return None
        if s.startswith("http://") or s.startswith("https://") or s.startswith("/"):
            return s
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
        image = record.get("image")
        images = record.get("images") or []
        normalized_image = _to_http_image_url(image)
        normalized_gallery: list[str] = []
        if isinstance(images, list):
            for img in images:
                resolved = _to_http_image_url(img)
                if resolved:
                    normalized_gallery.append(resolved)
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
    records = (
        db.list_owner_listings(principal.subject, limit=safe_limit)
        if mine
        else db.list_recent_listings(limit=safe_limit, include_analysis=False, include_media=True)
    )
    records = [_normalize_listing_media(record) for record in records]

    if include_matches and not mine:
        def _norm_brand(value: object) -> str:
            return str(value or "").strip().casefold()

        my_active = [
            _normalize_listing_media(x)
            for x in db.list_owner_listings(principal.subject, limit=200)
            if str(x.get("status", "")).lower() == "active"
        ]
        for record in records:
            base_value = float(record.get("estimated_value") or 0)
            if base_value <= 0:
                record["matches"] = []
                continue
            # Keep marketplace "matches" aligned with offer-candidate rules so
            # clicking Start Trade does not lead to zero eligible listings.
            tolerance = max(50.0, base_value * 0.30)
            owner_subject = str(record.get("owner_subject") or "")
            target_brand = _norm_brand(record.get("brand"))
            matches: list[dict] = []
            for candidate in my_active:
                if str(candidate.get("listing_id") or "") == str(record.get("listing_id") or ""):
                    continue
                candidate_owner_subject = str(candidate.get("owner_subject") or "")
                if owner_subject and candidate_owner_subject and owner_subject == candidate_owner_subject:
                    # Never return same-owner listings as matches.
                    continue
                candidate_value = float(candidate.get("estimated_value") or 0)
                if candidate_value <= 0:
                    continue
                if abs(candidate_value - base_value) > tolerance:
                    continue
                candidate_brand = _norm_brand(candidate.get("brand"))
                if target_brand and candidate_brand and target_brand != candidate_brand:
                    continue
                matches.append(candidate)
                if len(matches) >= 12:
                    break
            record["matches"] = matches
    return {
        "count": len(records),
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
        if not isinstance(value, str):
            return None
        s = value.strip()
        if not s or s.startswith("blob:"):
            return None
        if s.startswith("http://") or s.startswith("https://") or s.startswith("/"):
            return s
        if s.startswith("s3://"):
            try:
                signed = _presign_s3_uri(s, settings)
            except Exception:
                signed = None
            return signed
        return None

    def _normalize_listing_media(record: dict) -> dict:
        image = record.get("image")
        images = record.get("images") or []
        normalized_image = _to_http_image_url(image)
        normalized_gallery: list[str] = []
        if isinstance(images, list):
            for img in images:
                resolved = _to_http_image_url(img)
                if resolved:
                    normalized_gallery.append(resolved)
        if normalized_image:
            record["image"] = normalized_image
        if normalized_gallery:
            record["images"] = normalized_gallery
        if not normalized_image and not normalized_gallery:
            record["image"] = None
            record["images"] = []
        return record

    def _norm_brand(value: object) -> str:
        return str(value or "").strip().casefold()

    target = db.get_listing_by_id(listing_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target listing not found")
    if str(target.get("owner_subject") or "") == principal.subject:
        raise HTTPException(status_code=400, detail="Cannot create a trade offer on your own listing")

    target_value = float(target.get("estimated_value") or 0)
    target_brand = _norm_brand(target.get("brand"))
    if target_value <= 0:
        return {"count": 0, "items": []}

    tolerance = max(50.0, target_value * 0.30)
    safe_limit = max(1, min(limit, 200))
    mine = db.list_owner_listings(principal.subject, limit=safe_limit)
    candidates: list[dict] = []
    for record in mine:
        if str(record.get("status") or "").lower() != "active":
            continue
        if str(record.get("listing_id") or "") == str(target.get("listing_id") or ""):
            continue
        cand_value = float(record.get("estimated_value") or 0)
        if cand_value <= 0:
            continue
        if abs(cand_value - target_value) > tolerance:
            continue
        cand_brand = _norm_brand(record.get("brand"))
        if target_brand and cand_brand and cand_brand != target_brand:
            continue
        candidates.append(_normalize_listing_media(record))

    return {"count": len(candidates), "items": candidates}


@app.put("/v1/listings/{listing_id}", response_model=ListingResponse)
def update_listing(
    listing_id: str,
    payload: ListingCreateRequest,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
):
    normalized_image, normalized_images = _normalize_listing_media_for_storage(
        db=db,
        image=payload.image,
        images=payload.images,
        source_item_id=payload.source_item_id,
    )
    updated = db.update_listing(
        listing_id=listing_id,
        owner_subject=principal.subject,
        title=payload.title,
        mode=payload.mode,
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
    return ListingResponse(**record)


@app.post("/v1/offers", response_model=OfferResponse)
def create_offer(
    payload: OfferCreateRequest,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
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
    if str(target.get("status", "")).lower() != "active":
        raise HTTPException(status_code=400, detail="Target listing is not active")
    target_value = float(target.get("estimated_value") or 0)
    if target_value <= 0:
        raise HTTPException(status_code=400, detail="Target listing must have a valid estimated value")
    offered_value_total = 0.0
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
        offered_value_total += offered_value
    pct_gap = abs(offered_value_total - target_value) / target_value
    if pct_gap > 0.30:
        raise HTTPException(status_code=400, detail="Offered total is outside the trade price band")

    offer = db.create_trade_offer(
        offer_id=str(uuid.uuid4()),
        target_listing_id=payload.target_listing_id,
        offered_listing_id=offered_ids[0],
        offered_listing_ids=offered_ids,
        from_subject=principal.subject,
        to_subject=target["owner_subject"],
        message=(payload.message or "").strip(),
    )
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
    listing_map = db.get_listings_by_ids(listing_ids)
    items: list[OfferWithListingsResponse] = []
    for offer in offers:
        target = listing_map.get(str(offer["target_listing_id"]))
        offered_ids = [x for x in (offer.get("offered_listing_ids") or []) if isinstance(x, str) and x.strip()]
        offered_listings = [listing_map.get(str(x)) for x in offered_ids]
        offered_listings = [x for x in offered_listings if x]
        offered = offered_listings[0] if offered_listings else listing_map.get(str(offer["offered_listing_id"]))
        if not target or not offered:
            continue
        items.append(
            OfferWithListingsResponse(
                offer_id=offer["offer_id"],
                target_listing_id=offer["target_listing_id"],
                offered_listing_id=offer["offered_listing_id"],
                offered_listing_ids=offered_ids or [offer["offered_listing_id"]],
                from_subject=offer["from_subject"],
                to_subject=offer["to_subject"],
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
    if payload.status == "accepted" and payload.receive_address is None:
        raise HTTPException(status_code=400, detail="Select receive shipping address while accepting trade")
    receive_address_payload = payload.receive_address.model_dump() if payload.receive_address else None
    updated = db.set_trade_offer_participant_action(
        offer_id=offer_id,
        actor_subject=principal.subject,
        status=payload.status,
        receive_address=receive_address_payload,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Offer not found")
    if str(updated.get("status") or "").lower() == "accepted":
        offered_ids = [x for x in (updated.get("offered_listing_ids") or []) if isinstance(x, str) and x.strip()]
        if not offered_ids and isinstance(updated.get("offered_listing_id"), str):
            offered_ids = [updated["offered_listing_id"]]
        db.mark_listings_traded([updated["target_listing_id"], *offered_ids])
        try:
            _auto_create_labels_for_accepted_offer_and_notify(db=db, offer=updated, settings=settings)
        except Exception:
            # Do not block offer acceptance if shipping providers/email providers are temporarily unavailable.
            pass
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


def _outbound_leg_for_subject(offer: dict, subject: str) -> tuple[str, str, str, str]:
    from_subject_offer = str(offer.get("from_subject") or "")
    to_subject_offer = str(offer.get("to_subject") or "")
    offered_ids = [x for x in (offer.get("offered_listing_ids") or []) if isinstance(x, str) and x.strip()]
    if not offered_ids and isinstance(offer.get("offered_listing_id"), str):
        offered_ids = [offer["offered_listing_id"]]
    target_listing_id = str(offer.get("target_listing_id") or "")
    if subject == from_subject_offer:
        return from_subject_offer, to_subject_offer, (offered_ids[0] if offered_ids else ""), target_listing_id
    return to_subject_offer, from_subject_offer, target_listing_id, (offered_ids[0] if offered_ids else "")


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


def _contact_complete(a: dict[str, str | None]) -> bool:
    return bool((a.get("email") or "").strip() and (a.get("phone") or "").strip())


def _shippo_quote_rate(
    *,
    settings: Settings,
    from_addr: dict[str, str | None],
    to_addr: dict[str, str | None],
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
            "weight": str(settings.shippo_parcel_weight_oz), "mass_unit": "oz",
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
            }
    except Exception:
        return {"status": "shippo_unavailable", "carrier": "USPS", "service_level": "Priority Mail", "debug": "exception while calling Shippo API"}


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
                "weight": str(settings.shippo_parcel_weight_oz),
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
    if not offered_ids:
        return []
    from_subject = str(offer.get("from_subject") or "")
    to_subject = str(offer.get("to_subject") or "")
    target_listing_id = str(offer.get("target_listing_id") or "")
    sender_profile = _subject_shipping_snapshot(db, from_subject, settings)
    receiver_profile = _subject_shipping_snapshot(db, to_subject, settings)

    created: list[dict] = []
    for offered_id in offered_ids:
        label_result_offer = _shippo_buy_label(
            settings=settings,
            from_addr=sender_profile,
            to_addr=receiver_profile,
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
    label_result_return = _shippo_buy_label(
        settings=settings,
        from_addr=receiver_profile,
        to_addr=sender_profile,
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

    quote = _shippo_quote_rate(settings=settings, from_addr=sender_profile, to_addr=receiver_profile)
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
    from_subject, to_subject, _, _ = _outbound_leg_for_subject(offer, principal.subject)
    from_addr = _subject_shipping_snapshot(db, from_subject, settings)
    to_addr = _receive_address_snapshot_from_offer(offer=offer, subject=to_subject, db=db, settings=settings)
    to_full = _subject_shipping_snapshot(db, to_subject, settings)
    to_addr["email"] = to_full.get("email")
    to_addr["phone"] = to_full.get("phone")
    quote = _shippo_quote_rate(settings=settings, from_addr=from_addr, to_addr=to_addr)
    return ShippingQuoteResponse(
        offer_id=offer_id,
        actor_subject=principal.subject,
        status=quote.get("status") or "unknown",
        carrier=quote.get("carrier") or "USPS",
        service_level=quote.get("service_level") or "Priority Mail",
        amount=quote.get("amount"),
        currency=quote.get("currency"),
        rate_id=quote.get("rate_id"),
        debug=quote.get("debug"),
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
):
    offer = db.get_trade_offer_by_id(offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    if principal.subject not in {offer.get("from_subject"), offer.get("to_subject")}:
        raise HTTPException(status_code=403, detail="Forbidden")
    shipments_all = [_hydrate_shipment_party_fields(db, s) for s in db.list_shipments_for_offer(offer_id)]
    shipments = _visible_shipments_for_subject(shipments=shipments_all, subject=principal.subject)
    return {"offer_id": offer_id, "count": len(shipments), "shipments": shipments}


@app.get("/v1/shipments/{shipment_id}/label")
def get_shipping_label_document(
    shipment_id: str,
    principal: AuthPrincipal = Depends(get_request_principal),
    db: Database = Depends(get_db),
):
    shipment = db.get_trade_shipment_by_id(shipment_id)
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    if principal.subject != shipment.get("from_subject"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return {
        "shipment_id": shipment.get("shipment_id"),
        "carrier": shipment.get("carrier"),
        "service_level": shipment.get("service_level"),
        "tracking_number": shipment.get("tracking_number"),
        "label_url": shipment.get("label_url"),
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
        staged_raw, staged_content_type, stage_debug = _stage_item_image(raw, file.content_type or "image/jpeg", settings)
        image_uuid = str(uuid.uuid4())
        ext = ".jpg" if staged_content_type == "image/jpeg" else (os.path.splitext(file.filename or "")[1] or ".jpg")
        filename = f"{image_uuid}{ext}"
        role_hint = "full_item" if idx == 0 else "close_up"
        storage_uri = storage.save_upload(
            item_id=item_id,
            filename=filename,
            content_type=staged_content_type,
            data=staged_raw,
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
            )
        )
        image_inputs.append(
            ImageInput(
                image_id=image_uuid,
                filename=file.filename or filename,
                content_type=staged_content_type,
                bytes_data=staged_raw,
                role_hint=role_hint,
            )
        )
        uploaded_refs.append(
            {
                "image_id": image_uuid,
                "storage_uri": storage_uri,
                "role_hint": role_hint,
                "staging": stage_debug,
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
        grade=user_condition_grade or "Good",
        confidence=1.0 if user_condition_grade is not None else 0.35,
        issues=[],
    )
    warnings = []
    if user_condition_grade is None:
        warnings.append("Condition set to Good by default. Select condition to improve pricing accuracy.")
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
        profile_result = gpt_item_profiler.profile_item(
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
