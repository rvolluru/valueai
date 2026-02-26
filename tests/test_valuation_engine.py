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
