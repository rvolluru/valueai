from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from brand.types import ImageInput
from condition.service import ConditionAnalyzer
from valuation import ValuationService
from valuation.types import ValuationRequest

from .db import Database, PersistedImage
from .deps import (
    get_brand_analyzer,
    get_condition_analyzer,
    get_db,
    get_settings,
    get_storage,
    get_valuation_service,
)
from .logging_utils import log_json
from .schemas import AnalyzeResponse, BrandOut, ConditionOut, HealthResponse, VersionResponse
from .settings import Settings
from .storage import Storage


app = FastAPI(title="ValueAI Fashion Analyzer", version="0.1.0")
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(STATIC_DIR)), name="ui")

VALID_CATEGORIES = {"clothes", "shoes", "handbag"}


def normalize_category(value: str | None) -> str | None:
    if value is None:
        return None
    norm = value.strip().casefold()
    if norm == "handbags":
        norm = "handbag"
    if norm not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail="category must be clothes|shoes|handbag")
    return norm


def require_api_key(
    x_api_key: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


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


@app.post("/v1/analyze", response_model=AnalyzeResponse, dependencies=[Depends(require_api_key)])
async def analyze(
    item_id: Annotated[str, Form(...)],
    images: Annotated[list[UploadFile], File(...)],
    category: Annotated[str | None, Form()] = None,
    item_description: Annotated[str | None, Form()] = None,
    purchase_year: Annotated[int | None, Form()] = None,
    debug: Annotated[bool, Form()] = False,
    settings: Settings = Depends(get_settings),
    db: Database = Depends(get_db),
    storage: Storage = Depends(get_storage),
    brand_analyzer=Depends(get_brand_analyzer),
    condition_analyzer: ConditionAnalyzer = Depends(get_condition_analyzer),
    valuation_service: ValuationService = Depends(get_valuation_service),
) -> AnalyzeResponse:
    category = normalize_category(category)
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

    valuation_payload = None
    valuation_debug = None
    if settings.valuation_enabled and brand_out.name != "unknown":
        valuation_request = ValuationRequest(
            item_id=item_id,
            brand=brand_out.name,
            brand_confidence=brand_out.confidence,
            category=category_out,
            condition_grade=condition_out.grade,
            condition_confidence=condition_out.confidence,
            issues=[issue.model_dump() for issue in condition_out.issues],
            item_description=item_description,
            title_hint=item_description,
            purchase_year=purchase_year,
        )
        valuation_result = valuation_service.evaluate(valuation_request, debug=debug)
        valuation_payload = valuation_service.serialize(valuation_result)
        valuation_debug = valuation_payload.pop("_debug", None)

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
            "input_hints": {
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
        valuation=valuation_payload,
        requested_photos=requested_photos,
        debug=debug_payload,
    )

    db.insert_analysis(str(uuid.uuid4()), item_id, response.model_dump())
    total = time.perf_counter() - t0
    log_json(
        "analysis_complete",
        item_id=item_id,
        timings={"total_ms": round(total * 1000, 2), "brand_ms": round(t_brand * 1000, 2), "condition_ms": round(t_cond * 1000, 2)},
        category=response.category,
        brand=response.brand.model_dump(),
        condition={"grade": response.condition.grade, "confidence": response.condition.confidence},
        valuation=response.valuation,
        requested_photos=response.requested_photos,
        thresholds={
            "accept": settings.brand_accept_score,
            "accept_low": settings.brand_accept_score_low,
            "gap_min": settings.brand_gap_min,
        },
    )
    return response
