from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv


# Ensure modules that read os.getenv() directly (e.g., valuation provider helpers)
# see values from the local .env file in dev.
load_dotenv(override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    api_key: str = "local-dev-key"
    version: str = "0.1.0"

    database_url: str = "sqlite:///./valueai.db"

    storage_backend: str = "local"  # local|s3
    local_storage_dir: str = "./.data"

    s3_bucket: str = "valueai-mvp"
    s3_region: str = "us-east-1"
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_force_path_style: bool = False

    brand_accept_score: int = 78
    brand_accept_score_low: int = 70
    brand_gap_min: int = 8
    brand_enable_logo_classifier: bool = False
    brand_enable_gpt_vision: bool = False
    brand_gpt_vision_model: str = "gpt-5"
    brand_gpt_vision_timeout_s: float = 20.0
    brand_debug: bool = False
    brand_detector_weights_path: str | None = None
    brand_logo_classifier_weights_path: str | None = None
    brand_force_logo_classifier: bool = False
    brand_logo_model_type: str = "efficientnet"
    brand_logo_yolo_weights_path: str | None = None
    brand_logo_yolo_confidence: float = 0.35
    gpt_item_profile_enabled: bool = True
    gpt_item_profile_provider_order: str = "gemini,openai"
    gpt_item_profile_model: str = "gpt-5"
    gpt_item_profile_gemini_model: str = "gemini-2.5-flash"
    gpt_item_profile_timeout_s: float = 25.0
    gpt_item_profile_max_images: int = Field(default=2, ge=1, le=4)
    gpt_item_profile_image_detail: str = "auto"
    gpt_item_profile_reasoning_effort: str = "low"

    condition_rembg_enabled: bool = False
    image_staging_enabled: bool = True
    image_staging_gemini_enabled: bool = True
    image_staging_gemini_model: str = "gemini-2.5-flash-image-preview"
    image_staging_gemini_timeout_s: float = 30.0
    image_staging_imagen_model: str = "imagen-3.0-capability-001"
    image_staging_vertexai_enabled: bool = True
    gcp_project_id: str | None = None
    gcp_location: str = "us-central1"
    condition_category_weights_path: str | None = None
    condition_grade_weights_path: str | None = None
    condition_force_category_classifier: bool = False
    condition_force_efficientnet: bool = False

    max_images_per_request: int = Field(default=4, ge=1, le=8)
    gemini_api_key: str | None = None
    openai_api_key: str | None = None

    clerk_enabled: bool = False
    clerk_issuer: str | None = None
    clerk_jwks_url: str | None = None
    clerk_audience: str | None = None
    clerk_authorized_parties: str | None = None
    clerk_jwt_leeway_seconds: int = 60
    cors_allow_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    valuation_enabled: bool = True
    valuation_providers: str = "stub"
    valuation_min_comps: int = 3
    valuation_max_comps: int = 25
    valuation_currency: str = "USD"

    instagram_graph_api_version: str = "v20.0"
    instagram_user_id: str | None = None
    instagram_access_token: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
