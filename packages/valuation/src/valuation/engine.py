from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any
from datetime import datetime, timezone
import re

from rapidfuzz import fuzz

from .types import MarketComp, ValuationRequest, ValuationResult


GRADE_MULTIPLIERS = {
    "New": 1.00,
    "LikeNew": 0.90,
    "Good": 0.75,
    "Fair": 0.55,
    "Poor": 0.35,
}

ISSUE_DEDUCTION_BY_SEVERITY = {
    "light": 0.03,
    "moderate": 0.07,
    "heavy": 0.15,
}

SOURCE_WEIGHTS = {
    "stub": 0.50,
    "brand_site": 0.92,
    "ebay": 0.95,
    "firecrawl_agent": 0.90,
    "poshmark": 0.85,
    "the_realreal": 0.95,
    "rebag": 0.98,
}

LISTED_TO_SOLD_DISCOUNT = {
    "stub": 0.85,
    "brand_site": 0.9,
    "ebay": 0.9,
    "firecrawl_agent": 0.85,
    "poshmark": 0.82,
    "the_realreal": 0.78,
    "rebag": 0.82,
}


@dataclass(slots=True)
class PricingConfig:
    min_comps: int = 3
    max_comps: int = 25
    currency: str = "USD"
    title_match_threshold: float = 80.0
    new_with_tags_brand_site_weight: float = 0.45
    retail_to_resale_factor_default: float = 0.80
    retail_to_resale_factor_handbag: float = 0.88
    retail_to_resale_factor_shoes: float = 0.80
    retail_to_resale_factor_clothes: float = 0.72
    max_retail_premium_ratio: float = 3.0


def _normalize_text(text: str | None) -> str:
    if not text:
        return ""
    normalized = re.sub(r"[^a-z0-9]+", " ", text.casefold())
    return " ".join(normalized.split())


def _brand_stripped_text(text: str, brand: str) -> str:
    text_tokens = _normalize_text(text).split()
    brand_tokens = set(_normalize_text(brand).split())
    if not text_tokens:
        return ""
    return " ".join(token for token in text_tokens if token not in brand_tokens)


def _reference_title(request: ValuationRequest) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for part in (request.item_description, request.title_hint, request.model_hint):
        if not part or not part.strip():
            continue
        cleaned = part.strip()
        normalized = _normalize_text(cleaned)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        parts.append(cleaned)
    return " ".join(parts)


CATEGORY_KEYWORDS = {
    "shoes": {
        "positive": {
            "shoe", "shoes", "heel", "heels", "pump", "pumps", "slingback", "slingbacks",
            "sandal", "sandals", "sneaker", "sneakers", "boot", "boots", "loafer", "loafers",
            "flat", "flats", "peep", "toe", "stiletto", "mule", "mules", "wedge", "wedges",
        },
        "negative": {
            "bag", "bags", "handbag", "handbags", "hobo", "tote", "satchel", "clutch",
            "crossbody", "wallet", "purse", "backpack", "duffle",
        },
    },
    "handbag": {
        "positive": {
            "bag", "bags", "handbag", "handbags", "hobo", "tote", "satchel", "clutch",
            "crossbody", "wallet", "purse", "backpack", "duffle", "shoulder",
        },
        "negative": {
            "shoe", "shoes", "heel", "heels", "pump", "pumps", "slingback", "slingbacks",
            "sandal", "sandals", "sneaker", "sneakers", "boot", "boots", "loafer", "loafers",
            "flat", "flats", "stiletto", "mule", "mules", "wedge", "wedges",
        },
    },
    "clothes": {
        "positive": {
            "dress", "dresses", "shirt", "shirts", "top", "tops", "blouse", "blouses",
            "jacket", "jackets", "coat", "coats", "pant", "pants", "jean", "jeans",
            "skirt", "skirts", "sweater", "sweaters", "hoodie", "hoodies",
        },
        "negative": {
            "bag", "bags", "handbag", "handbags", "hobo", "tote", "satchel", "clutch",
            "crossbody", "wallet", "purse", "shoe", "shoes", "heel", "heels", "pump",
            "pumps", "slingback", "slingbacks", "sandal", "sandals", "sneaker", "sneakers",
            "boot", "boots",
        },
    },
}


def _token_set(text: str) -> set[str]:
    normalized = _normalize_text(text)
    return set(normalized.split()) if normalized else set()


def _category_mismatch_reason(request: ValuationRequest, title: str, reference: str) -> str | None:
    category_key = (request.category or "").strip().lower()
    keywords = CATEGORY_KEYWORDS.get(category_key)
    if not keywords:
        return None

    title_tokens = _token_set(title)
    reference_tokens = _token_set(reference)
    if not title_tokens:
        return None

    positive = keywords["positive"]
    negative = keywords["negative"]

    ref_positive = reference_tokens & positive
    title_positive = title_tokens & positive
    title_negative = title_tokens & negative

    if ref_positive and title_negative and not title_positive:
        return "category_keyword_mismatch"
    return None


def _filter_comps_by_title_similarity(
    request: ValuationRequest, comps: list[MarketComp], threshold: float
) -> tuple[list[MarketComp], list[dict[str, Any]], dict[str, Any]]:
    reference = _reference_title(request)
    if not reference:
        return comps, [], {"applied": False, "reason": "no_reference_title"}

    reference_full = _normalize_text(reference)
    reference_core = _brand_stripped_text(reference, request.brand)
    filtered: list[MarketComp] = []
    rejected: list[dict[str, Any]] = []

    for comp in comps:
        mismatch_reason = _category_mismatch_reason(request, comp.title, reference)
        if mismatch_reason:
            rejected.append(
                {
                    "source": comp.source,
                    "title": comp.title,
                    "price": comp.price,
                    "url": comp.url,
                    "rejection_reason": mismatch_reason,
                }
            )
            continue
        title_full = _normalize_text(comp.title)
        title_core = _brand_stripped_text(comp.title, request.brand)
        full_score = max(
            fuzz.token_set_ratio(reference_full, title_full),
            fuzz.token_sort_ratio(reference_full, title_full),
        )
        core_score = (
            max(
                fuzz.token_set_ratio(reference_core, title_core),
                fuzz.token_sort_ratio(reference_core, title_core),
            )
            if reference_core and title_core
            else 0.0
        )
        score = max(core_score, full_score * 0.85)
        comp.metadata["title_match_score"] = round(score, 2)
        comp.metadata["title_match_core_score"] = round(core_score, 2)
        comp.metadata["title_match_full_score"] = round(full_score, 2)
        if score >= threshold:
            filtered.append(comp)
            continue
        rejected.append(
            {
                "source": comp.source,
                "title": comp.title,
                "price": comp.price,
                "url": comp.url,
                "title_match_score": round(score, 2),
                "title_match_core_score": round(core_score, 2),
                "title_match_full_score": round(full_score, 2),
            }
        )

    if filtered:
        return filtered, rejected, {
            "applied": True,
            "reference_title": reference,
            "threshold": threshold,
            "kept_count": len(filtered),
            "rejected_count": len(rejected),
        }

    return comps, rejected, {
        "applied": True,
        "reference_title": reference,
        "threshold": threshold,
        "kept_count": len(comps),
        "rejected_count": len(rejected),
        "fallback_reason": "all_comps_below_threshold",
    }


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    idx = (len(sorted_values) - 1) * p
    lo = int(idx)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = idx - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def _trim_outliers(comps: list[MarketComp]) -> tuple[list[MarketComp], list[MarketComp], dict[str, Any]]:
    if len(comps) < 4:
        return comps, [], {"method": "none", "reason": "too_few_comps"}
    values = sorted(c.price for c in comps if c.price > 0)
    if len(values) < 4:
        return comps, [], {"method": "none", "reason": "too_few_positive_prices"}
    q1 = _percentile(values, 0.25)
    q3 = _percentile(values, 0.75)
    iqr = q3 - q1
    lo = q1 - 1.5 * iqr
    hi = q3 + 1.5 * iqr
    kept = [c for c in comps if lo <= c.price <= hi]
    removed = [c for c in comps if c not in kept]
    if not kept:
        kept = comps
        removed = []
    return kept, removed, {
        "method": "iqr",
        "q1": round(q1, 2),
        "q3": round(q3, 2),
        "iqr": round(iqr, 2),
        "lower": round(lo, 2),
        "upper": round(hi, 2),
    }


def _condition_multiplier(grade: str) -> float:
    return GRADE_MULTIPLIERS.get(grade, 0.75)


def _issue_deduction(issues: list[dict[str, Any]]) -> tuple[float, list[dict[str, Any]]]:
    total = 0.0
    details: list[dict[str, Any]] = []
    for issue in issues:
        sev = str(issue.get("severity", "light")).lower()
        deduction = ISSUE_DEDUCTION_BY_SEVERITY.get(sev, 0.03)
        total += deduction
        details.append(
            {
                "type": issue.get("type", "unknown"),
                "severity": sev,
                "deduction": round(deduction, 3),
            }
        )
    total = min(total, 0.35)
    return total, details


def _confidence(request: ValuationRequest, selected_comps: list[MarketComp], spread_ratio: float) -> float:
    if not selected_comps:
        return 0.0
    comp_count_score = min(1.0, len(selected_comps) / 10.0)
    source_score = sum(SOURCE_WEIGHTS.get(c.source, 0.7) for c in selected_comps) / len(selected_comps)
    spread_score = max(0.1, 1.0 - min(spread_ratio, 1.0))
    identity_score = 0.85 if (request.model_hint or request.title_hint or request.item_description) else 0.45
    purchase_year_score = 0.8 if request.purchase_year else 0.45
    score = (
        0.22 * request.brand_confidence
        + 0.18 * request.condition_confidence
        + 0.22 * comp_count_score
        + 0.17 * source_score
        + 0.09 * spread_score
        + 0.07 * identity_score
        + 0.05 * purchase_year_score
    )
    return round(max(0.0, min(score, 0.99)), 3)


def _purchase_year_adjustment(request: ValuationRequest, base_value: float) -> tuple[float, dict[str, Any]]:
    year = request.purchase_year
    if not year:
        return 1.0, {"applied": False}
    current_year = datetime.now(timezone.utc).year
    age = max(0, current_year - int(year))

    # Conservative generic depreciation proxy when exact model-era comps are not available.
    category_floor = {"handbag": 0.65, "shoes": 0.55, "clothes": 0.50}.get(request.category, 0.55)
    if age <= 1:
        factor = 1.0
    elif age <= 3:
        factor = 0.97
    elif age <= 5:
        factor = 0.93
    elif age <= 10:
        factor = 0.88
    else:
        factor = max(category_floor, 0.88 - 0.015 * (age - 10))

    # Avoid over-discounting luxury collectible bags without model-aware comps.
    if request.category == "handbag" and request.brand_confidence >= 0.85:
        factor = max(factor, 0.75)

    return factor, {
        "applied": True,
        "purchase_year": int(year),
        "item_age_years": age,
        "factor": round(factor, 3),
    }


def _retail_reference_price(comps: list[MarketComp]) -> float | None:
    retail_prices: list[float] = []
    for comp in comps:
        if comp.source == "brand_site":
            original = comp.metadata.get("original_list_price")
            if isinstance(original, (int, float)) and original > 0:
                retail_prices.append(float(original))
            elif comp.price > 0:
                retail_prices.append(float(comp.price))
            continue
        if comp.source == "firecrawl_agent" and comp.metadata.get("market_kind") == "new" and comp.price > 0:
            retail_prices.append(float(comp.price))
    return float(median(retail_prices)) if retail_prices else None


def _retail_to_resale_factor(category: str | None, config: PricingConfig) -> float:
    category_key = (category or "").strip().lower()
    if category_key == "handbag":
        return config.retail_to_resale_factor_handbag
    if category_key == "shoes":
        return config.retail_to_resale_factor_shoes
    if category_key == "clothes":
        return config.retail_to_resale_factor_clothes
    return config.retail_to_resale_factor_default


def estimate_value(
    request: ValuationRequest, comps: list[MarketComp], config: PricingConfig, debug: bool = False
) -> ValuationResult:
    comps, similarity_rejected, similarity_meta = _filter_comps_by_title_similarity(
        request, comps, config.title_match_threshold
    )
    retail_reference = _retail_reference_price(comps)
    sold = [c for c in comps if c.is_sold and c.price > 0]
    listed_only = [c for c in comps if (not c.is_sold) and c.price > 0]
    using_listed_fallback = False
    if not sold and listed_only:
        sold = [
            MarketComp(
                source=c.source,
                title=c.title,
                price=round(c.price * LISTED_TO_SOLD_DISCOUNT.get(c.source, 0.8), 2),
                currency=c.currency,
                is_sold=False,
                condition_text=c.condition_text,
                sold_at=c.sold_at,
                listed_at=c.listed_at,
                url=c.url,
                metadata={
                    **c.metadata,
                    "original_list_price": c.price,
                    "listed_fallback_discount": LISTED_TO_SOLD_DISCOUNT.get(c.source, 0.8),
                },
            )
            for c in listed_only
        ]
        using_listed_fallback = True
    if not sold:
        return ValuationResult(
            estimated_value=None,
            currency=config.currency,
            range_low=None,
            range_high=None,
            confidence=0.0,
            basis="no_comps",
            comps_summary={"count": 0, "source_breakdown": {}},
            resale_market_value=None,
            retail_reference_value=None,
            debug={"reason": "No sold or listed comps available"} if debug else {},
        )

    sold = sold[: config.max_comps]
    selected, removed, trim_meta = _trim_outliers(sold)
    prices = [c.price for c in selected]
    resale_selected = [
        c
        for c in selected
        if not (
            c.source == "brand_site"
            or (c.source == "firecrawl_agent" and c.metadata.get("market_kind") == "new")
        )
    ]
    base_resale = float(median([c.price for c in resale_selected])) if resale_selected else float(median(prices))
    base = base_resale
    blend_meta: dict[str, Any] = {"applied": False}
    if (
        request.condition_grade == "New"
        and retail_reference is not None
        and resale_selected
    ):
        retail_factor = _retail_to_resale_factor(request.category, config)
        adjusted_retail_reference = retail_reference * retail_factor
        premium_ratio = adjusted_retail_reference / max(base_resale, 1.0)
        weight = max(0.0, min(config.new_with_tags_brand_site_weight, 0.6))
        if premium_ratio > config.max_retail_premium_ratio:
            weight *= max(0.0, config.max_retail_premium_ratio / premium_ratio)
        base = (base_resale * (1.0 - weight)) + (adjusted_retail_reference * weight)
        blend_meta = {
            "applied": True,
            "resale_reference_value": round(base_resale, 2),
            "retail_reference_value": round(retail_reference, 2),
            "retail_resale_equivalent_value": round(adjusted_retail_reference, 2),
            "retail_to_resale_factor": round(retail_factor, 3),
            "premium_ratio": round(premium_ratio, 3),
            "max_retail_premium_ratio": round(config.max_retail_premium_ratio, 3),
            "retail_reference_weight": round(weight, 3),
            "resale_weight": round(1.0 - weight, 3),
            "blended_base_value": round(base, 2),
        }
    cond_mult = _condition_multiplier(request.condition_grade)
    issue_deduction, issue_details = _issue_deduction(request.issues)
    purchase_year_factor, purchase_year_meta = _purchase_year_adjustment(request, base)
    adjusted = base * cond_mult * (1.0 - issue_deduction) * purchase_year_factor
    spread = (max(prices) - min(prices)) / max(base, 1.0) if prices else 1.0
    conf = _confidence(request, selected, spread_ratio=spread)
    low = adjusted * 0.85
    high = adjusted * 1.15
    if len(selected) < config.min_comps:
        conf = round(min(conf, 0.45), 3)
        low = adjusted * 0.75
        high = adjusted * 1.25

    source_breakdown: dict[str, int] = {}
    for c in selected:
        source_breakdown[c.source] = source_breakdown.get(c.source, 0) + 1

    debug_payload: dict[str, Any] = {}
    if debug:
        debug_payload = {
            "base_market_value_median": round(base, 2),
            "resale_reference_value": round(base_resale, 2),
            "retail_reference_blend": blend_meta,
            "condition_multiplier": round(cond_mult, 3),
            "issue_deduction_total": round(issue_deduction, 3),
            "issue_deductions": issue_details,
            "purchase_year_adjustment": purchase_year_meta,
            "spread_ratio": round(spread, 3),
            "title_similarity_filter": similarity_meta,
            "rejected_low_similarity_comps": similarity_rejected,
            "outlier_filter": trim_meta,
            "removed_outliers": [
                {"source": c.source, "title": c.title, "price": c.price} for c in removed
            ],
            "selected_comps": [
                {
                    "source": c.source,
                    "title": c.title,
                    "price": c.price,
                    "url": c.url,
                    "title_match_score": c.metadata.get("title_match_score"),
                }
                for c in selected
            ],
        }
        if using_listed_fallback:
            debug_payload["used_listed_fallback"] = True

    return ValuationResult(
        estimated_value=round(adjusted, 2),
        currency=config.currency,
        range_low=round(low, 2),
        range_high=round(high, 2),
        confidence=conf,
        basis=(
            "blended_resale_and_retail_reference_with_condition_adjustment"
            if blend_meta.get("applied")
            else (
                "listed_comps_discounted_to_sold_equivalent_with_condition_adjustment"
                if using_listed_fallback
                else "median_sold_comps_with_condition_adjustment"
            )
        ),
        comps_summary={
            "count": len(selected),
            "median_sold_price": round(base, 2),
            "source_breakdown": source_breakdown,
        },
        resale_market_value=round(base_resale, 2),
        retail_reference_value=round(retail_reference, 2) if retail_reference is not None else None,
        debug=debug_payload,
    )
