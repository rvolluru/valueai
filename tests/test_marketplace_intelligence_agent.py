from datetime import datetime, timezone

from app.marketplace_intelligence_agent import build_marketplace_intelligence_report


def _listing(listing_id: str, owner: str, category: str, value: float, status: str = "Active") -> dict:
    return {
        "listing_id": listing_id,
        "owner_subject": owner,
        "category": category,
        "estimated_value": value,
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def test_marketplace_report_separates_inventory_and_demand_popularity() -> None:
    listings = [
        _listing("bag-1", "a", "Handbag", 500),
        _listing("bag-2", "b", "Handbag", 520),
        _listing("shoe-1", "c", "Shoes", 510),
    ]
    offers = [
        {"target_listing_id": "shoe-1"},
        {"target_listing_id": "shoe-1"},
        {"target_listing_id": "bag-1"},
    ]

    report = build_marketplace_intelligence_report(listings, offers)

    assert report["leaders"]["inventory_category"]["category"] == "Handbag"
    assert report["leaders"]["demand_category"]["category"] == "Shoes"
    assert report["summary"]["match_coverage_pct"] == 100.0


def test_marketplace_report_excludes_same_owner_from_available_matches() -> None:
    listings = [
        _listing("one", "same-user", "Clothes", 200),
        _listing("two", "same-user", "Clothes", 205),
        _listing("three", "other-user", "Shoes", 600),
    ]

    report = build_marketplace_intelligence_report(listings, [])

    assert report["summary"]["valued_active_listings"] == 3
    assert report["summary"]["listings_with_matches"] == 0
    assert report["summary"]["active_listings_without_matches"] == 3
    assert report["summary"]["match_coverage_pct"] == 0.0
    reasons = {item["reason_code"]: item["listings"] for item in report["unmatched_inventory"]["reason_counts"]}
    assert reasons["same_owner_only"] == 2
    assert reasons["outside_value_tolerance"] == 1


def test_marketplace_report_groups_values_and_unvalued_items() -> None:
    listings = [
        _listing("unknown", "a", "Accessories", 0),
        _listing("low", "b", "Accessories", 80),
        _listing("mid", "c", "Handbag", 750),
        _listing("high", "d", "Jewelry", 6000),
    ]

    report = build_marketplace_intelligence_report(listings, [])
    bands = {item["key"]: item for item in report["value_bands"]}

    assert bands["unknown"]["listings"] == 1
    assert bands["under_100"]["listings"] == 1
    assert bands["500_999"]["listings"] == 1
    assert bands["5000_plus"]["listings"] == 1
    reasons = {item["reason_code"]: item["listings"] for item in report["unmatched_inventory"]["reason_counts"]}
    assert reasons["missing_valuation"] == 1
    assert report["summary"]["active_listings_without_matches"] == 4
