from __future__ import annotations

from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, Field


ConditionGrade: TypeAlias = Literal["NewWithTags", "New", "LikeNew"]


class BrandOut(BaseModel):
    name: str
    confidence: float
    evidence: str


class IssueOut(BaseModel):
    type: str
    severity: str
    location: str = "unknown"


class ConditionOut(BaseModel):
    grade: ConditionGrade
    confidence: float
    issues: list[IssueOut] = Field(default_factory=list)


class UploadedImageOut(BaseModel):
    image_id: str
    role_hint: str | None = None
    storage_uri: str
    image_url: str


class AnalyzeResponse(BaseModel):
    item_id: str
    category: Literal["clothes", "shoes", "handbag", "accessories"]
    brand: BrandOut
    condition: ConditionOut
    user_condition: ConditionGrade | None = None
    valuation: dict[str, Any] | None = None
    item_profile: dict[str, Any] | None = None
    requested_photos: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    uploaded_images: list[UploadedImageOut] = Field(default_factory=list)
    debug: dict[str, Any] | None = None


class UploadImagesResponse(BaseModel):
    item_id: str
    uploaded_images: list[UploadedImageOut] = Field(default_factory=list)


class ImageRoleClassification(BaseModel):
    image_index: int = Field(ge=0)
    role: str
    confidence: float = Field(ge=0, le=1)


class ImageRoleClassificationResponse(BaseModel):
    category: str
    category_confidence: float = Field(ge=0, le=1)
    images: list[ImageRoleClassification] = Field(default_factory=list)
    required_roles: list[str] = Field(default_factory=list)
    recommended_roles: list[str] = Field(default_factory=list)
    missing_required: list[str] = Field(default_factory=list)
    missing_recommended: list[str] = Field(default_factory=list)
    elapsed_ms: float
    warning: str | None = None


class PresignImageUploadItem(BaseModel):
    filename: str | None = None
    content_type: str = "image/jpeg"
    content_length: int | None = Field(default=None, ge=0)


class PresignImageUploadRequest(BaseModel):
    item_id: str | None = None
    images: list[PresignImageUploadItem] = Field(default_factory=list)


class PresignedImageUploadSlot(BaseModel):
    image_id: str
    role_hint: str | None = None
    storage_uri: str
    image_url: str
    upload_url: str
    method: str = "PUT"
    headers: dict[str, str] = Field(default_factory=dict)
    expires_in: int = 900


class PresignImageUploadResponse(BaseModel):
    item_id: str
    upload_slots: list[PresignedImageUploadSlot] = Field(default_factory=list)


class ConfirmPresignedImageUploadItem(BaseModel):
    image_id: str
    filename: str | None = None
    content_type: str = "image/jpeg"
    storage_uri: str
    role_hint: str | None = None
    content_hash: str | None = None


class ConfirmPresignedImageUploadRequest(BaseModel):
    item_id: str
    uploaded_images: list[ConfirmPresignedImageUploadItem] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str


class DependencyHealthCheck(BaseModel):
    name: str
    status: Literal["ok", "degraded", "down", "not_configured"]
    latency_ms: float | None = None
    message: str | None = None
    checked_at: str


class DependencyHealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down"]
    checks: list[DependencyHealthCheck] = Field(default_factory=list)


class VersionResponse(BaseModel):
    version: str


class ShippingAddress(BaseModel):
    label: str | None = None
    full_name: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    is_default: bool = False


class UserProfileQuizUpdateRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    gender: Literal["female", "male", "other"] | None = None
    birthday: str | None = None
    tops_size: str | None = None
    dresses_size: str | None = None
    bottoms_size: str | None = None
    shoes_size: str | None = None
    category_preferences: list[str] = Field(default_factory=list)
    style_descriptors: list[str] = Field(default_factory=list)
    jouft_goals: list[str] = Field(default_factory=list)
    shipping_full_name: str | None = None
    shipping_address_line1: str | None = None
    shipping_address_line2: str | None = None
    shipping_city: str | None = None
    shipping_state: str | None = None
    shipping_postal_code: str | None = None
    shipping_country: str | None = None
    shipping_email: str | None = None
    shipping_phone: str | None = None
    shipping_addresses: list[ShippingAddress] = Field(default_factory=list)
    subscription_plan: str | None = None
    subscription_billing_cycle: Literal["monthly", "annual"] | None = None
    subscription_status: str | None = None
    subscription_renewal_date: str | None = None
    payment_methods: list[str] = Field(default_factory=list)


class UserProfileQuizResponse(UserProfileQuizUpdateRequest):
    owner_subject: str
    created_at: str
    updated_at: str


class ClientStateUpdateRequest(BaseModel):
    alert_preferences: dict[str, bool] | None = None
    liked_listing_ids: list[str] | None = None


class ClientStateResponse(BaseModel):
    owner_subject: str
    alert_preferences: dict[str, bool] = Field(default_factory=dict)
    liked_listing_ids: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str


class UserNotificationResponse(BaseModel):
    notification_id: str
    owner_subject: str
    actor_subject: str | None = None
    type: str
    title: str
    body: str
    entity_id: str | None = None
    action_tab: str | None = None
    created_at: str


class AdminSupportNoteCreateRequest(BaseModel):
    entity_type: Literal["listing", "analysis", "trade", "billing", "user"]
    entity_id: str
    category: Literal["valuation_dispute", "auth_risk", "refund", "trade_support", "analysis_support", "general"]
    status: Literal["open", "investigating", "resolved", "rejected"] = "open"
    note: str = ""


class ExperienceEventCreateRequest(BaseModel):
    event_name: Literal[
        "screen_viewed",
        "profile_started",
        "profile_saved",
        "listing_started",
        "listing_photos_added",
        "listing_photo_check_failed",
        "listing_analysis_started",
        "listing_analysis_failed",
        "listing_created",
        "listing_published",
        "marketplace_listing_viewed",
        "trade_composer_started",
        "trade_offer_submitted",
        "support_started",
        "support_submitted",
        "ui_error",
    ]
    session_id: str = Field(min_length=1, max_length=100)
    platform: Literal["web", "ios", "android"]
    screen: str | None = Field(default=None, max_length=80)
    entity_type: Literal["listing", "trade", "profile", "support"] | None = None
    entity_id: str | None = Field(default=None, max_length=120)
    properties: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class PushTokenRegisterRequest(BaseModel):
    token: str
    device_id: str | None = None
    platform: str | None = None


class PaymentMethodCreateRequest(BaseModel):
    method_type: Literal["card", "apple_pay", "paypal", "link"]
    provider: Literal["stripe", "paypal"] = "stripe"
    label: str | None = None
    last4: str | None = None
    brand: str | None = None
    exp_month: int | None = None
    exp_year: int | None = None
    email: str | None = None
    provider_token: str | None = None
    is_default: bool = False


class StripeAttachPaymentMethodRequest(BaseModel):
    payment_method_id: str
    is_default: bool = False


class PaymentMethodResponse(BaseModel):
    payment_method_id: str
    owner_subject: str
    provider: str
    method_type: Literal["card", "apple_pay", "paypal", "link"]
    label: str | None = None
    last4: str | None = None
    brand: str | None = None
    exp_month: int | None = None
    exp_year: int | None = None
    email: str | None = None
    is_default: bool = False
    created_at: str
    updated_at: str


class PaymentMethodListResponse(BaseModel):
    items: list[PaymentMethodResponse] = Field(default_factory=list)


class SubscriptionActivateRequest(BaseModel):
    plan: Literal["free", "starter_15", "pro_25"]
    billing_cycle: Literal["monthly", "annual"] = "monthly"
    payment_method_id: str | None = None


class SubscriptionActivateResponse(BaseModel):
    owner_subject: str
    plan: str
    billing_cycle: str
    status: str
    renewal_date: str | None = None
    stripe_subscription_id: str | None = None
    message: str | None = None


class StripeSetupIntentResponse(BaseModel):
    provider: str = "stripe"
    client_secret: str | None = None
    customer_id: str | None = None
    publishable_key: str | None = None
    status: str
    message: str | None = None


class StripeSetupCheckoutRequest(BaseModel):
    success_url: str
    cancel_url: str


class StripeSetupCheckoutResponse(BaseModel):
    provider: str = "stripe"
    checkout_url: str | None = None
    session_id: str | None = None
    status: str
    message: str | None = None


class AuthMeResponse(BaseModel):
    provider: str = "clerk"
    user_id: str
    email: str | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    claims: dict[str, Any] | None = None


class ListedImage(BaseModel):
    p_img: str | None = None
    d_img: str | None = None
    is_hero: bool = False


class ListingCreateRequest(BaseModel):
    title: str
    mode: Literal["trade"] = "trade"
    category: Literal["clothes", "shoes", "handbag", "accessories"]
    brand: str
    condition: ConditionGrade
    size: str | None = None
    estimated_value: float = Field(ge=0)
    city: str = "Your area"
    image: str | None = None
    images: list[str] = Field(default_factory=list)
    listed_images: list[ListedImage] = Field(default_factory=list)
    description: str = ""
    wants: str = "Open to similar-value offers"
    tags: list[str] = Field(default_factory=list)
    source_item_id: str | None = None
    analysis: dict[str, Any] | None = None
    status: Literal["Analyzing", "Review", "AnalysisFailed", "Active", "Traded"] = "Review"


class ListingResponse(ListingCreateRequest):
    listing_id: str
    owner_subject: str
    owner_name: str | None = None
    created_at: str


class ListingSupportRequest(BaseModel):
    reason: Literal[
        "incorrect_brand_or_title",
        "incorrect_valuation",
        "incorrect_condition",
        "missing_product_information",
        "image_processing_problem",
        "authentication_concern",
        "other",
    ]
    message: str = Field(min_length=10, max_length=4000)
    contact_email: str = Field(min_length=3, max_length=320)
    contact_name: str | None = Field(default=None, max_length=200)
    platform: Literal["web", "ios", "android"] | None = None
    app_version: str | None = Field(default=None, max_length=100)


class ListingSupportResponse(BaseModel):
    status: Literal["submitted"] = "submitted"
    thread_id: str
    listing_id: str


class OfferCreateRequest(BaseModel):
    target_listing_id: str
    offered_listing_id: str | None = None
    offered_listing_ids: list[str] = Field(default_factory=list)
    message: str = ""


class OfferResponse(BaseModel):
    offer_id: str
    target_listing_id: str
    offered_listing_id: str
    offered_listing_ids: list[str] = Field(default_factory=list)
    selected_offered_listing_id: str | None = None
    from_subject: str
    to_subject: str
    from_name: str | None = None
    to_name: str | None = None
    status: Literal["pending", "accepted", "declined", "countered", "cancelled"] = "pending"
    accepted_by_from: bool = False
    accepted_by_to: bool = False
    from_receive_address: ShippingAddress | None = None
    to_receive_address: ShippingAddress | None = None
    message: str = ""
    created_at: str
    updated_at: str


class OfferWithListingsResponse(OfferResponse):
    target_listing: ListingResponse
    offered_listing: ListingResponse
    offered_listings: list[ListingResponse] = Field(default_factory=list)


class TradeMatchResponse(BaseModel):
    match_id: str
    viewer_subject: str
    target_listing_id: str
    candidate_listing_id: str
    score: float
    confidence: float
    rationale: str
    risk_flags: list[str] = Field(default_factory=list)
    status: Literal["suggested", "dismissed", "offered", "expired"] = "suggested"
    agent_version: str
    created_at: str
    updated_at: str
    target_listing: ListingResponse | None = None
    candidate_listing: ListingResponse | None = None


class TradeMatchRunResponse(BaseModel):
    status: Literal["ok", "disabled"] = "ok"
    generated_count: int
    expired_count: int = 0
    items: list[TradeMatchResponse] = Field(default_factory=list)


class TradeMatchListResponse(BaseModel):
    count: int
    items: list[TradeMatchResponse] = Field(default_factory=list)


class TradeMatchStatusUpdateRequest(BaseModel):
    status: Literal["suggested", "dismissed", "offered", "expired"]


class OfferActionRequest(BaseModel):
    status: Literal["accepted", "declined", "countered", "cancelled"]
    receive_address: ShippingAddress | None = None
    selected_offered_listing_id: str | None = None


class ShippingQuoteResponse(BaseModel):
    offer_id: str
    actor_subject: str
    status: str
    carrier: str
    service_level: str
    amount: str | None = None
    currency: str | None = None
    rate_id: str | None = None
    debug: str | None = None


class ShippingLabelCreateRequest(BaseModel):
    confirmed: bool = True
    rate_id: str | None = None


class InstagramShareResponse(BaseModel):
    status: Literal["queued", "published"]
    listing_id: str
    creation_id: str | None = None
    media_id: str | None = None
    detail: str | None = None
