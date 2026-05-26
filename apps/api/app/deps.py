from __future__ import annotations

from functools import lru_cache

from brand import BrandAnalyzer, BrandConfig
from condition import ConditionAnalyzer, ConditionConfig
from valuation import ValuationConfig, ValuationService

from .db import Database
from .gpt_item_profile import GptItemProfiler
from .settings import Settings, get_settings
from .storage import Storage, build_storage


@lru_cache(maxsize=1)
def get_db() -> Database:
    db = Database(get_settings().database_url)
    db.initialize()
    try:
        db.migrate_listing_media_urls_to_http()
    except Exception:
        # Non-fatal: API should still start even if migration encounters a bad row.
        pass
    return db


@lru_cache(maxsize=1)
def get_storage() -> Storage:
    return build_storage(get_settings())


@lru_cache(maxsize=1)
def get_brand_analyzer() -> BrandAnalyzer:
    s = get_settings()
    return BrandAnalyzer(
        BrandConfig(
            accept_score=s.brand_accept_score,
            accept_score_low=s.brand_accept_score_low,
            gap_min=s.brand_gap_min,
            enable_logo_classifier=s.brand_enable_logo_classifier,
            enable_gpt_vision=s.brand_enable_gpt_vision,
            gpt_vision_model=s.brand_gpt_vision_model,
            gpt_vision_timeout_s=s.brand_gpt_vision_timeout_s,
            openai_api_key=s.openai_api_key,
            debug_default=s.brand_debug,
            detector_weights_path=s.brand_detector_weights_path,
            logo_classifier_weights_path=s.brand_logo_classifier_weights_path,
            force_logo_classifier=s.brand_force_logo_classifier,
            logo_model_type=s.brand_logo_model_type,
            logo_yolo_weights_path=s.brand_logo_yolo_weights_path,
            logo_yolo_confidence=s.brand_logo_yolo_confidence,
        )
    )


@lru_cache(maxsize=1)
def get_condition_analyzer() -> ConditionAnalyzer:
    s = get_settings()
    return ConditionAnalyzer(
        ConditionConfig(
            rembg_enabled=s.condition_rembg_enabled,
            category_model_weights_path=s.condition_category_weights_path,
            condition_model_weights_path=s.condition_grade_weights_path,
            force_category_classifier=s.condition_force_category_classifier,
            force_efficientnet=s.condition_force_efficientnet,
        )
    )


@lru_cache(maxsize=1)
def get_valuation_service() -> ValuationService:
    s = get_settings()
    providers = [p.strip() for p in s.valuation_providers.split(",") if p.strip()]
    return ValuationService(
        ValuationConfig(
            enabled=s.valuation_enabled,
            providers=providers or ["stub"],
            currency=s.valuation_currency,
            min_comps=s.valuation_min_comps,
            max_comps=s.valuation_max_comps,
        )
    )


@lru_cache(maxsize=1)
def get_gpt_item_profiler() -> GptItemProfiler:
    s = get_settings()
    return GptItemProfiler(
        enabled=s.gpt_item_profile_enabled,
        provider_order=s.gpt_item_profile_provider_order,
        openai_api_key=s.openai_api_key,
        openai_model=s.gpt_item_profile_model,
        gemini_api_key=s.gemini_api_key,
        gemini_model=s.gpt_item_profile_gemini_model,
        timeout_s=s.gpt_item_profile_timeout_s,
        max_images=s.gpt_item_profile_max_images,
        image_detail=s.gpt_item_profile_image_detail,
        reasoning_effort=s.gpt_item_profile_reasoning_effort,
    )
