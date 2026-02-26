from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class BrandOut(BaseModel):
    name: str
    confidence: float
    evidence: str


class IssueOut(BaseModel):
    type: str
    severity: str
    location: str = "unknown"


class ConditionOut(BaseModel):
    grade: Literal["New", "LikeNew", "Good", "Fair", "Poor"]
    confidence: float
    issues: list[IssueOut] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    item_id: str
    category: Literal["clothes", "shoes", "handbag"]
    brand: BrandOut
    condition: ConditionOut
    valuation: dict[str, Any] | None = None
    requested_photos: list[str] = Field(default_factory=list)
    debug: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: str


class VersionResponse(BaseModel):
    version: str
