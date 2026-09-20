from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median

from .trade_match_agent import _trade_match_tolerance


VALUE_BANDS = [
    ("under_100", "Under $100", 0.01, 100.0),
    ("100_249", "$100-$249", 100.0, 250.0),
    ("250_499", "$250-$499", 250.0, 500.0),
    ("500_999", "$500-$999", 500.0, 1000.0),
    ("1000_2499", "$1,000-$2,499", 1000.0, 2500.0),
    ("2500_4999", "$2,500-$4,999", 2500.0, 5000.0),
    ("5000_plus", "$5,000+", 5000.0, float("inf")),
]


def _clean(value: object, fallback: str = "Unknown") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _value(value: object) -> float:
    try:
        return max(float(value or 0), 0.0)
    except (TypeError, ValueError):
        return 0.0


def _value_band(value: float) -> tuple[str, str]:
    if value <= 0:
        return "unknown", "No valuation"
    for key, label, low, high in VALUE_BANDS:
        if low <= value < high:
            return key, label
    return "unknown", "No valuation"


def _parse_timestamp(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def build_marketplace_intelligence_report(listings: list[dict], offers: list[dict], *, days: int = 30) -> dict:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    valid = [item for item in listings if str(item.get("listing_id") or "").strip()]
    active = [item for item in valid if _clean(item.get("status"), "").casefold() == "active"]
    recent = [item for item in valid if (_parse_timestamp(item.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc)) >= since]

    category_counts = Counter(_clean(item.get("category")) for item in valid)
    active_category_counts = Counter(_clean(item.get("category")) for item in active)
    recent_category_counts = Counter(_clean(item.get("category")) for item in recent)
    target_ids = Counter(_clean(offer.get("target_listing_id"), "") for offer in offers)
    listing_by_id = {_clean(item.get("listing_id"), ""): item for item in valid}
    category_offer_counts = Counter()
    for listing_id, count in target_ids.items():
        target = listing_by_id.get(listing_id)
        if target:
            category_offer_counts[_clean(target.get("category"))] += count

    categories = []
    for category in sorted(category_counts, key=lambda key: (-category_counts[key], key.casefold())):
        listed = category_counts[category]
        received = category_offer_counts[category]
        active_count = active_category_counts[category]
        categories.append({
            "category": category,
            "listings": listed,
            "active_listings": active_count,
            "recent_listings": recent_category_counts[category],
            "inventory_share_pct": round((listed / len(valid)) * 100, 1) if valid else 0.0,
            "offers_received": received,
            "offers_per_active_listing": round(received / active_count, 2) if active_count else 0.0,
        })

    band_counts = Counter(_value_band(_value(item.get("estimated_value")))[0] for item in valid)
    active_band_counts = Counter(_value_band(_value(item.get("estimated_value")))[0] for item in active)
    value_bands = []
    all_bands = [("unknown", "No valuation"), *((key, label) for key, label, _, _ in VALUE_BANDS)]
    for key, label in all_bands:
        value_bands.append({
            "key": key,
            "label": label,
            "listings": band_counts[key],
            "active_listings": active_band_counts[key],
            "share_pct": round((band_counts[key] / len(valid)) * 100, 1) if valid else 0.0,
        })

    valued_active = [item for item in active if _value(item.get("estimated_value")) > 0]
    sorted_values = sorted(_value(item.get("estimated_value")) for item in valued_active)
    sorted_valued_items = sorted(
        ((_value(item.get("estimated_value")), _clean(item.get("owner_subject"), "")) for item in valued_active),
        key=lambda item: item[0],
    )
    owner_values: dict[str, list[float]] = defaultdict(list)
    for item in valued_active:
        owner_values[_clean(item.get("owner_subject"), "")].append(_value(item.get("estimated_value")))
    for values in owner_values.values():
        values.sort()

    matches_per_listing = []
    match_counts_by_category: dict[str, list[int]] = defaultdict(list)
    unmatched_listings = []
    unmatched_reason_counts: Counter[str] = Counter()
    valued_by_owner = Counter(_clean(item.get("owner_subject"), "") for item in valued_active)

    def nearest_other_value(value: float, owner: str) -> float | None:
        position = bisect_left(sorted_values, value)
        left, right = position - 1, position
        while left >= 0 or right < len(sorted_valued_items):
            left_distance = abs(sorted_valued_items[left][0] - value) if left >= 0 else float("inf")
            right_distance = abs(sorted_valued_items[right][0] - value) if right < len(sorted_valued_items) else float("inf")
            if left_distance <= right_distance:
                candidate_value, candidate_owner = sorted_valued_items[left]
                left -= 1
            else:
                candidate_value, candidate_owner = sorted_valued_items[right]
                right += 1
            if candidate_owner != owner:
                return candidate_value
        return None

    for item in valued_active:
        value = _value(item.get("estimated_value"))
        tolerance, _ = _trade_match_tolerance(value)
        low, high = value - tolerance, value + tolerance
        total_in_band = bisect_right(sorted_values, high) - bisect_left(sorted_values, low)
        owner = _clean(item.get("owner_subject"), "")
        same_owner_values = owner_values.get(owner, [])
        same_owner_in_band = bisect_right(same_owner_values, high) - bisect_left(same_owner_values, low)
        available = max(total_in_band - same_owner_in_band, 0)
        category = _clean(item.get("category"))
        matches_per_listing.append(available)
        match_counts_by_category[category].append(available)
        if available == 0:
            nearest_value = nearest_other_value(value, owner)
            if len(valued_active) - valued_by_owner[owner] <= 0:
                reason_code = "no_other_owner_inventory"
                reason = "No valued active listings from another user are available."
                nearest_value = None
            elif same_owner_in_band > 1 and same_owner_in_band == total_in_band:
                reason_code = "same_owner_only"
                reason = "Only this user's own listings fall inside the allowed value range."
            else:
                reason_code = "outside_value_tolerance"
                reason = f"The nearest other-user listing is ${nearest_value:,.0f}, outside the allowed ${max(low, 0):,.0f}-${high:,.0f} range."
            unmatched_reason_counts[reason_code] += 1
            unmatched_listings.append({
                "listing_id": _clean(item.get("listing_id"), ""),
                "title": _clean(item.get("title"), "Untitled listing"),
                "brand": _clean(item.get("brand")),
                "category": category,
                "estimated_value": value,
                "reason_code": reason_code,
                "reason": reason,
                "allowed_value_low": round(max(low, 0), 2),
                "allowed_value_high": round(high, 2),
                "nearest_other_value": round(nearest_value, 2) if nearest_value is not None else None,
            })

    for item in active:
        if _value(item.get("estimated_value")) > 0:
            continue
        unmatched_reason_counts["missing_valuation"] += 1
        unmatched_listings.append({
            "listing_id": _clean(item.get("listing_id"), ""),
            "title": _clean(item.get("title"), "Untitled listing"),
            "brand": _clean(item.get("brand")),
            "category": _clean(item.get("category")),
            "estimated_value": 0.0,
            "reason_code": "missing_valuation",
            "reason": "The listing has no positive valuation, so a value-compatible match cannot be calculated.",
            "allowed_value_low": None,
            "allowed_value_high": None,
            "nearest_other_value": None,
        })

    zero_match_count = sum(1 for count in matches_per_listing if count == 0)
    match_categories = []
    for category, counts in sorted(match_counts_by_category.items(), key=lambda item: item[0].casefold()):
        with_matches = sum(1 for count in counts if count > 0)
        match_categories.append({
            "category": category,
            "valued_active_listings": len(counts),
            "listings_with_matches": with_matches,
            "coverage_pct": round((with_matches / len(counts)) * 100, 1) if counts else 0.0,
            "median_available_matches": round(float(median(counts)), 1) if counts else 0.0,
        })

    inventory_leader = categories[0] if categories else None
    demand_leader = max(categories, key=lambda item: (item["offers_received"], item["offers_per_active_listing"]), default=None)
    return {
        "generated_at": now.isoformat(),
        "window_days": days,
        "summary": {
            "total_listings": len(valid),
            "active_listings": len(active),
            "recent_listings": len(recent),
            "valued_active_listings": len(valued_active),
            "listings_with_matches": len(matches_per_listing) - zero_match_count,
            "active_listings_without_matches": len(unmatched_listings),
            "match_coverage_pct": round(((len(matches_per_listing) - zero_match_count) / len(active)) * 100, 1) if active else 0.0,
            "median_available_matches": round(float(median(matches_per_listing)), 1) if matches_per_listing else 0.0,
            "offers": len(offers),
        },
        "leaders": {
            "inventory_category": inventory_leader,
            "demand_category": demand_leader if demand_leader and demand_leader["offers_received"] > 0 else None,
        },
        "categories": categories,
        "value_bands": value_bands,
        "match_coverage_by_category": match_categories,
        "unmatched_inventory": {
            "total": len(unmatched_listings),
            "reason_counts": [
                {"reason_code": code, "label": {
                    "missing_valuation": "Missing valuation",
                    "no_other_owner_inventory": "No other-user inventory",
                    "same_owner_only": "Only own items in range",
                    "outside_value_tolerance": "Outside value tolerance",
                }.get(code, code.replace("_", " ").title()), "listings": count}
                for code, count in unmatched_reason_counts.most_common()
            ],
            "listings": sorted(unmatched_listings, key=lambda item: (-item["estimated_value"], item["title"]))[:100],
            "truncated": len(unmatched_listings) > 100,
        },
        "definitions": {
            "inventory_popularity": "Category with the most listings in the current database.",
            "demand_popularity": "Category receiving the most trade offers.",
            "available_match": "Another owner's active, valued listing within the same value-tolerance rule used by trade matching.",
        },
    }
