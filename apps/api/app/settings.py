from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv


# Ensure modules that read os.getenv() directly (e.g., valuation provider helpers)
# see values from the local .env file in dev.
load_dotenv(override=False)

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _normalize_sqlite_database_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw.startswith("sqlite:///"):
        return raw
    # `sqlite:////abs/path.db` -> absolute path, keep as is.
    path_part = raw.replace("sqlite:///", "", 1)
    if path_part.startswith("/"):
        return raw
    # Resolve relative sqlite paths against repo root so local runs use one DB.
    abs_path = (_REPO_ROOT / path_part).resolve()
    return f"sqlite:///{abs_path}"


def _normalize_local_storage_dir(path: str) -> str:
    raw = str(path or "").strip()
    if not raw:
        return str((_REPO_ROOT / ".data").resolve())
    p = Path(raw)
    if p.is_absolute():
        return str(p.resolve())
    return str((_REPO_ROOT / p).resolve())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str((_REPO_ROOT / ".env").resolve()), ".env"),
        extra="ignore",
    )

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
    image_staging_photoroom_enabled: bool = True
    photoroom_api_key: str | None = None
    photoroom_segment_url: str = "https://sdk.photoroom.com/v1/segment"
    photoroom_timeout_s: float = 20.0
    photoroom_output_format: str = "jpg"
    photoroom_background_color: str = "#FFFFFF"
    photoroom_output_size: str = "full"
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

    max_images_per_request: int = Field(default=6, ge=1, le=8)
    gemini_api_key: str | None = None
    openai_api_key: str | None = None

    clerk_enabled: bool = False
    clerk_issuer: str | None = None
    clerk_jwks_url: str | None = None
    clerk_audience: str | None = None
    clerk_authorized_parties: str | None = None
    clerk_jwt_leeway_seconds: int = 60
    cors_allow_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:5174,http://127.0.0.1:5174,"
        "http://localhost:5175,http://127.0.0.1:5175"
    )

    valuation_enabled: bool = True
    valuation_providers: str = "stub"
    valuation_min_comps: int = 3
    valuation_max_comps: int = 25
    valuation_currency: str = "USD"

    trade_match_agent_enabled: bool = True
    trade_match_agent_max_targets: int = Field(default=100, ge=1, le=500)
    trade_match_agent_max_user_items: int = Field(default=200, ge=1, le=500)
    trade_match_agent_max_matches_per_listing: int = Field(default=3, ge=1, le=10)

    instagram_graph_api_version: str = "v20.0"
    instagram_user_id: str | None = None
    instagram_access_token: str | None = None

    usps_addresses_api_url: str = "https://apis.usps.com/addresses/v3/address"
    usps_bearer_token: str | None = None
    usps_timeout_s: float = 8.0
    stripe_secret_key: str | None = None
    stripe_publishable_key: str | None = None
    paypal_client_id: str | None = None
    shippo_api_key: str | None = None
    shippo_api_base_url: str = "https://api.goshippo.com"
    shippo_parcel_weight_oz: float = 32.0
    shippo_default_contact_email: str | None = None
    shippo_default_contact_phone: str | None = None
    email_provider: str = "auto"  # auto|ses|smtp
    ses_region: str | None = None
    ses_from_email: str | None = None
    ses_endpoint_url: str | None = None
    ses_access_key_id: str | None = None
    ses_secret_access_key: str | None = None
    ses_session_token: str | None = None
    ses_template_shipping_label: str | None = "jouft-shipping-label-v1"
    ses_template_subscription: str | None = "jouft-subscription-v1"
    ses_template_signup_welcome: str | None = "jouft-signup-welcome-v1"
    ses_template_forgot_password: str | None = "jouft-forgot-password-v1"
    ses_template_offer_update: str | None = "jouft-offer-update-v1"
    ses_template_shipping_reminder: str | None = "jouft-shipping-reminder-v1"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_use_tls: bool = True
    shipping_reminder_enabled: bool = True
    shipping_reminder_interval_hours: int = 24
    shipping_reminder_poll_seconds: int = 3600
    shipping_reminder_auto_track: bool = True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.database_url = _normalize_sqlite_database_url(settings.database_url)
    settings.local_storage_dir = _normalize_local_storage_dir(settings.local_storage_dir)
    return settings
