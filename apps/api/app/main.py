from __future__ import annotations

import json
import os
import re
import time
import uuid
from io import BytesIO
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

import boto3
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
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
    UploadedImageOut,
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

    if not normalized_images and source_item_id:
        fallback_ids = db.list_image_ids_for_item(source_item_id, limit=8)
        if fallback_ids:
            normalized_images = [f"/v1/images/{img_id}" for img_id in fallback_ids]

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
    if path.exists():
        return FileResponse(path)
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
        size=payload.size,
        estimated_value=payload.estimated_value,
        city=payload.city,
        image=normalized_image,
        images=normalized_images,
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

    safe_limit = max(1, min(limit, 100))
    records = (
        db.list_owner_listings(principal.subject, limit=safe_limit)
        if mine
        else db.list_recent_listings(limit=safe_limit, include_analysis=False, include_media=True)
    )
    for record in records:
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
        if has_valid_image or has_valid_gallery:
            continue
        source_item_id = record.get("source_item_id")
        if not source_item_id:
            continue
        fallback_image_ids = db.list_image_ids_for_item(source_item_id, limit=8)
        if fallback_image_ids:
            fallback_urls = [f"/v1/images/{img_id}" for img_id in fallback_image_ids]
            record["image"] = fallback_urls[0]
            record["images"] = fallback_urls
    return {
        "count": len(records),
        "items": records,
        "actor": {"auth_type": principal.auth_type, "subject": principal.subject},
    }


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
