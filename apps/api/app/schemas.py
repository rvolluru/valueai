from __future__ import annotations

from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, Field


ConditionGrade: TypeAlias = Literal["New", "LikeNew", "Good", "Fair", "Poor"]


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


class AnalyzeResponse(BaseModel):
    item_id: str
    category: Literal["clothes", "shoes", "handbag"]
    brand: BrandOut
    condition: ConditionOut
    user_condition: ConditionGrade | None = None
    valuation: dict[str, Any] | None = None
    item_profile: dict[str, Any] | None = None
    requested_photos: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    debug: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: str


class VersionResponse(BaseModel):
    version: str


class AuthMeResponse(BaseModel):
    provider: str = "clerk"
    user_id: str
    email: str | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    claims: dict[str, Any] | None = None


class ListingCreateRequest(BaseModel):
    title: str
    mode: Literal["sell", "trade", "sell_trade"] = "sell_trade"
    category: Literal["clothes", "shoes", "handbag"]
    brand: str
    condition: ConditionGrade
    estimated_value: float = Field(ge=0)
    city: str = "Your area"
    image: str | None = None
    wants: str = "Open to similar-value offers"
    tags: list[str] = Field(default_factory=list)
    source_item_id: str | None = None
    analysis: dict[str, Any] | None = None


class ListingResponse(ListingCreateRequest):
    listing_id: str
    owner_subject: str
    owner_name: str | None = None
    created_at: str
