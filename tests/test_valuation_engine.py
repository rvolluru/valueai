from valuation.engine import PricingConfig, estimate_value
from valuation.types import MarketComp, ValuationRequest


def _req(grade: str = "Good", issues=None) -> ValuationRequest:
    return ValuationRequest(
        item_id="item-1",
        brand="Nike",
        brand_confidence=0.9,
        category="shoes",
        condition_grade=grade,
        condition_confidence=0.8,
        issues=issues or [],
    )


def test_estimate_value_uses_median_and_condition_adjustment() -> None:
    comps = [
        MarketComp(source="stub", title="a", price=100),
        MarketComp(source="stub", title="b", price=120),
        MarketComp(source="stub", title="c", price=140),
        MarketComp(source="stub", title="d", price=1000),  # outlier
    ]
    result = estimate_value(_req("Good"), comps, PricingConfig(), debug=True)
    assert result.estimated_value is not None
    assert result.currency == "USD"
    assert result.estimated_value < 200
    assert result.range_low < result.estimated_value < result.range_high
    assert result.comps_summary["count"] >= 3


def test_issue_deductions_reduce_value() -> None:
    comps = [MarketComp(source="stub", title=str(i), price=p) for i, p in enumerate([100, 110, 120, 130])]
    no_issue = estimate_value(_req("Good", []), comps, PricingConfig())
    with_issue = estimate_value(
        _req("Good", [{"type": "scuffs", "severity": "heavy"}]),
        comps,
        PricingConfig(),
    )
    assert no_issue.estimated_value is not None
    assert with_issue.estimated_value is not None
    assert with_issue.estimated_value < no_issue.estimated_value


def test_listed_comps_fallback_produces_value_when_no_sold_comps() -> None:
    comps = [
        MarketComp(source="rebag", title="a", price=1000, is_sold=False),
        MarketComp(source="the_realreal", title="b", price=900, is_sold=False),
        MarketComp(source="poshmark", title="c", price=800, is_sold=False),
    ]
    result = estimate_value(_req("Good"), comps, PricingConfig(), debug=True)
    assert result.estimated_value is not None
    assert result.basis.startswith("listed_comps_discounted")
    assert result.debug.get("used_listed_fallback") is True


def test_purchase_year_adjustment_reduces_value_for_older_item() -> None:
    comps = [MarketComp(source="stub", title=str(i), price=p) for i, p in enumerate([100, 110, 120, 130])]
    recent_req = _req("Good")
    recent_req.purchase_year = 2024
    old_req = _req("Good")
    old_req.purchase_year = 2008
    recent = estimate_value(recent_req, comps, PricingConfig(), debug=True)
    old = estimate_value(old_req, comps, PricingConfig(), debug=True)
    assert recent.estimated_value is not None and old.estimated_value is not None
    assert old.estimated_value < recent.estimated_value
    assert old.debug["purchase_year_adjustment"]["applied"] is True


def test_title_similarity_filter_rejects_unrelated_marketplace_comp() -> None:
    req = _req("New")
    req.brand = "Louis Vuitton"
    req.item_description = "Louis Vuitton 1854 Neverfull MM Handbag"
    comps = [
        MarketComp(
            source="poshmark",
            title="Louis Vuitton 1854 Neverfull MM Handbag",
            price=3465,
            is_sold=False,
        ),
        MarketComp(
            source="poshmark",
            title="LOUIS VUITTON Monogram Saint Cloud MM Shoulder Bag M51243 LV Auth BA8879",
            price=960,
            is_sold=False,
        ),
        MarketComp(
            source="poshmark",
            title="Authentic Louis Vuitton Neverfull MM Tote",
            price=1650,
            is_sold=False,
        ),
    ]
    result = estimate_value(req, comps, PricingConfig(), debug=True)

    selected_titles = [comp["title"] for comp in result.debug["selected_comps"]]
    rejected_titles = [comp["title"] for comp in result.debug["rejected_low_similarity_comps"]]

    assert "Louis Vuitton 1854 Neverfull MM Handbag" in selected_titles
    assert (
        "LOUIS VUITTON Monogram Saint Cloud MM Shoulder Bag M51243 LV Auth BA8879"
        in rejected_titles
    )
    assert "Authentic Louis Vuitton Neverfull MM Tote" in rejected_titles
    assert result.debug["title_similarity_filter"]["applied"] is True


def test_reference_title_dedupes_overlapping_request_fields() -> None:
    req = _req("New")
    req.brand = "Jimmy Choo"
    req.item_description = "Jimmy Choo Bing crystal mule"
    req.title_hint = "Jimmy Choo Bing crystal mule"
    comps = [
        MarketComp(
            source="poshmark",
            title="Jimmy Choo Bing crystal mule",
            price=500.0,
            is_sold=False,
        ),
        MarketComp(
            source="poshmark",
            title="Jimmy Choo Bing 65 crystal mule",
            price=550.0,
            is_sold=False,
        ),
        MarketComp(
            source="poshmark",
            title="Jimmy Choo satin clutch",
            price=250.0,
            is_sold=False,
        ),
    ]

    result = estimate_value(req, comps, PricingConfig(), debug=True)

    assert result.debug["title_similarity_filter"]["reference_title"] == "Jimmy Choo Bing crystal mule"


def test_new_item_blends_brand_site_reference_with_resale_comps() -> None:
    req = _req("New")
    req.brand = "Jimmy Choo"
    req.item_description = "Gold Liquid Metal Leather Slingbacks with Jimmy Choo Perforated Corsage"
    comps = [
        MarketComp(
            source="brand_site",
            title="Gold Liquid Metal Leather Slingbacks With Jimmy Choo Perforated Corsage",
            price=1035.0,
            is_sold=False,
            metadata={"original_list_price": 1150.0, "listed_fallback_discount": 0.9},
        ),
        MarketComp(
            source="poshmark",
            title="Gold Liquid Metal Leather Slingbacks With Jimmy Choo Perforated Corsage",
            price=400.0,
            is_sold=False,
        ),
        MarketComp(
            source="poshmark",
            title="Gold Liquid Metal Leather Slingbacks With Jimmy Choo Perforated Corsage",
            price=500.0,
            is_sold=False,
        ),
        MarketComp(
            source="poshmark",
            title="Gold Liquid Metal Leather Slingbacks With Jimmy Choo Perforated Corsage",
            price=600.0,
            is_sold=False,
        ),
    ]

    result = estimate_value(req, comps, PricingConfig(), debug=True)

    assert result.estimated_value is not None
    assert result.basis == "blended_resale_and_retail_reference_with_condition_adjustment"
    assert result.debug["retail_reference_blend"]["applied"] is True
    assert result.debug["retail_reference_blend"]["resale_reference_value"] == 410.0
    assert result.debug["retail_reference_blend"]["retail_reference_value"] == 1150.0
    assert result.debug["retail_reference_blend"]["retail_resale_equivalent_value"] == 920.0
    assert result.debug["retail_reference_blend"]["retail_to_resale_factor"] == 0.8
    assert result.debug["retail_reference_blend"]["blended_base_value"] == 639.5
    assert result.estimated_value == 639.5
    assert result.resale_market_value == 410.0
    assert result.retail_reference_value == 1150.0


def test_new_item_reduces_brand_site_weight_when_gap_is_too_large() -> None:
    req = _req("New")
    req.brand = "Coach"
    req.category = "shoes"
    req.item_description = "Coach Signature Slingback Heels"
    comps = [
        MarketComp(
            source="brand_site",
            title="Coach Signature Slingback Heels",
            price=2700.0,
            is_sold=False,
            metadata={"original_list_price": 3000.0, "listed_fallback_discount": 0.9},
        ),
        MarketComp(source="poshmark", title="Coach Signature Slingback Heels", price=300.0, is_sold=False),
        MarketComp(source="poshmark", title="Coach Signature Slingback Heels", price=350.0, is_sold=False),
        MarketComp(source="poshmark", title="Coach Signature Slingback Heels", price=400.0, is_sold=False),
    ]

    result = estimate_value(req, comps, PricingConfig(), debug=True)

    assert result.estimated_value is not None
    assert result.debug["retail_reference_blend"]["applied"] is True
    assert result.debug["retail_reference_blend"]["premium_ratio"] > 3.0
    assert result.debug["retail_reference_blend"]["retail_reference_weight"] < 0.45


def test_firecrawl_agent_new_and_resale_signals_feed_retail_and_resale_references() -> None:
    req = _req("New")
    req.brand = "Jimmy Choo"
    req.item_description = "Gold Liquid Metal Leather Slingbacks with Jimmy Choo Perforated Corsage"
    comps = [
        MarketComp(
            source="firecrawl_agent",
            title="Gold Liquid Metal Leather Slingbacks with Jimmy Choo Perforated Corsage",
            price=900.0,
            is_sold=False,
            metadata={"market_kind": "new", "comp_count": 5},
        ),
        MarketComp(
            source="firecrawl_agent",
            title="Gold Liquid Metal Leather Slingbacks with Jimmy Choo Perforated Corsage",
            price=500.0,
            is_sold=True,
            metadata={"market_kind": "resale", "comp_count": 8},
        ),
        MarketComp(
            source="poshmark",
            title="Gold Liquid Metal Leather Slingbacks with Jimmy Choo Perforated Corsage",
            price=450.0,
            is_sold=False,
        ),
        MarketComp(
            source="rebag",
            title="Gold Liquid Metal Leather Slingbacks with Jimmy Choo Perforated Corsage",
            price=550.0,
            is_sold=False,
        ),
    ]

    result = estimate_value(req, comps, PricingConfig(), debug=True)

    assert result.estimated_value is not None
    assert result.basis == "blended_resale_and_retail_reference_with_condition_adjustment"
    assert result.resale_market_value == 500.0
    assert result.retail_reference_value == 900.0
    assert result.debug["retail_reference_blend"]["retail_reference_value"] == 900.0
    assert result.debug["retail_reference_blend"]["resale_reference_value"] == 500.0


def test_shoe_request_rejects_handbag_comps_even_with_same_brand() -> None:
    req = _req("New")
    req.brand = "Jimmy Choo"
    req.category = "shoes"
    req.item_description = "Gold Liquid Metal Leather Slingbacks with Jimmy Choo Perforated Corsage"
    comps = [
        MarketComp(
            source="poshmark",
            title="Jimmy Choo Gold Slingback Heels with Pointed Toe",
            price=491.18,
            is_sold=False,
        ),
        MarketComp(
            source="rebag",
            title="Jimmy Choo Rosalie Convertible Satchel Perforated Leather Large",
            price=323.9,
            is_sold=False,
        ),
    ]

    result = estimate_value(req, comps, PricingConfig(), debug=True)

    selected_titles = [comp["title"] for comp in result.debug["selected_comps"]]
    rejected = result.debug["rejected_low_similarity_comps"]

    assert "Jimmy Choo Gold Slingback Heels with Pointed Toe" in selected_titles
    assert any(
        item["title"] == "Jimmy Choo Rosalie Convertible Satchel Perforated Leather Large"
        and item["rejection_reason"] == "category_keyword_mismatch"
        for item in rejected
    )
