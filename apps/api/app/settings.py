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

    condition_rembg_enabled: bool = False
    condition_category_weights_path: str | None = None
    condition_grade_weights_path: str | None = None

    max_images_per_request: int = Field(default=4, ge=1, le=8)
    openai_api_key: str | None = None

    valuation_enabled: bool = True
    valuation_providers: str = "stub"
    valuation_min_comps: int = 3
    valuation_max_comps: int = 25
    valuation_currency: str = "USD"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
