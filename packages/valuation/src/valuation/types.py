from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MarketComp:
    source: str
    title: str
    price: float
    currency: str = "USD"
    is_sold: bool = True
    condition_text: str | None = None
    sold_at: str | None = None
    listed_at: str | None = None
    url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ValuationRequest:
    brand: str
    brand_confidence: float
    category: str
    condition_grade: str
    condition_confidence: float
    issues: list[dict[str, Any]]
    item_id: str | None = None
    title_hint: str | None = None
    item_description: str | None = None
    model_hint: str | None = None
    size: str | None = None
    material: str | None = None
    color: str | None = None
    purchase_year: int | None = None


@dataclass(slots=True)
class ValuationResult:
    estimated_value: float | None
    currency: str
    range_low: float | None
    range_high: float | None
    confidence: float
    basis: str
    comps_summary: dict[str, Any]
    resale_market_value: float | None = None
    retail_reference_value: float | None = None
    debug: dict[str, Any] = field(default_factory=dict)
