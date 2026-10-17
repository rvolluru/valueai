import pytest
from app.pricing_evidence import validate_valuation
from app.pricing_evidence import source_title_supports, tokens
from app.main import valuation_from_gpt_item_profile

URL = "https://shop.example/items/1"
IDENTITY = {"candidate_brand": "John Varvatos", "candidate_model": "Alice Cooper Leather Biker"}


def sample():
    row = dict(url=URL, brand="John Varvatos", model="Alice Cooper Leather Biker", variant_match="confirmed",
               condition="LikeNew", price_type="asking", price=600, currency="USD", match_type="exact", match_evidence="Named collaboration and leather biker variant")
    data = dict(pricing_comparables=[row], resale_price_estimate=dict(estimated_price=550, condition_grade="LikeNew", references=[dict(url=URL)]),
                retail_price_estimate=dict(estimated_price=1600), resale_price_breakdown=[dict(estimated_price=550)])
    raw = {"output": [{"type": "message", "content": [{"annotations": [dict(type="url_citation", url=URL, title="John Varvatos Alice Cooper Leather Biker")]}]}]}
    return data, raw


def test_exact_supported_title_passes():
    data, raw = sample()
    assert validate_valuation(data, IDENTITY, raw)["pricing_evidence_policy"]["status"] == "qualified"


@pytest.mark.parametrize("field,value", [("brand", "Other"), ("model", "Star USA Jacket"),
    ("variant_match", "unconfirmed"), ("match_type", "related"), ("price_type", "retail"), ("price", -1)])
def test_wrong_comparables_fail_closed(field, value):
    data, raw = sample()
    data["pricing_comparables"][0][field] = value
    result = validate_valuation(data, IDENTITY, raw)
    assert result["pricing_evidence_policy"]["status"] == "needs_review"
    assert result["retail_price_estimate"]["estimated_price"] is None
    assert result["resale_price_breakdown"] == []
    assert valuation_from_gpt_item_profile(result, default_currency="USD", condition_grade="LikeNew") is None


def test_model_claim_without_search_support_not_enough():
    data, raw = sample()
    assert validate_valuation(data, IDENTITY, {})["pricing_evidence_policy"]["status"] == "needs_review"
    raw["output"][0]["content"][0]["annotations"][0]["title"] = "John Varvatos Star USA Jacket"
    assert validate_valuation(data, IDENTITY, raw)["pricing_evidence_policy"]["status"] == "needs_review"


def test_unqualified_extra_anchor_rejects_entire_price():
    data, raw = sample()
    data["resale_price_estimate"]["references"].append({"url": "https://shop.example/other-model"})
    assert validate_valuation(data, IDENTITY, raw)["pricing_evidence_policy"]["status"] == "needs_review"


def test_legacy_cached_price_cannot_bypass_new_policy():
    from app.main import _cached_analysis_is_strong_enough_for_reuse
    legacy = {"brand": {"name": "Known", "confidence": .99},
              "item_profile": {"model_identification": {"name": "Known model"}}}
    assert not _cached_analysis_is_strong_enough_for_reuse(legacy)


def test_qualified_policy_does_not_allow_retail_percentage_fallback():
    data, raw = sample()
    result = validate_valuation(data, IDENTITY, raw)
    result["resale_price_estimate"]["estimated_price"] = None
    result["resale_price_breakdown"] = []
    assert valuation_from_gpt_item_profile(result, default_currency="USD", condition_grade="LikeNew") is None


def related_sample():
    data, raw = sample()
    row = data["pricing_comparables"][0]
    row.update(model="Barron Studded Leather Jacket", match_type="related", variant_match="unconfirmed",
               similarity_basis="Same-brand studded leather biker with comparable construction and material.",
               adjustment_explanation="Different collaboration; no Alice Cooper collector premium assumed, adjust for used condition.")
    raw["output"][0]["content"][0]["annotations"][0]["title"] = "John Varvatos Barron Studded Leather Jacket"
    return data, raw


def test_same_brand_similar_model_does_not_require_review():
    data, raw = related_sample()
    result = validate_valuation(data, IDENTITY, raw)
    assert result["pricing_evidence_policy"]["status"] == "qualified"
    assert result["pricing_evidence_policy"]["basis"] == "same_brand_similar_model"
    assert result["resale_price_estimate"]["estimated_price"] == 550


@pytest.mark.parametrize("field", ["similarity_basis", "adjustment_explanation"])
def test_related_models_need_explanation(field):
    data, raw = related_sample()
    data["pricing_comparables"][0][field] = ""
    assert validate_valuation(data, IDENTITY, raw)["pricing_evidence_policy"]["status"] == "needs_review"


def test_different_brand_still_excluded_with_similarity_explanation():
    data, raw = related_sample()
    data["pricing_comparables"][0]["brand"] = "Other Brand"
    assert validate_valuation(data, IDENTITY, raw)["pricing_evidence_policy"]["status"] == "needs_review"


def test_same_brand_same_product_title_may_use_different_model_name():
    data, raw = related_sample()
    raw["output"][0]["content"][0]["annotations"][0]["title"] = "John Varvatos Alice Cooper Leather Biker"
    assert validate_valuation(data, IDENTITY, raw)["pricing_evidence_policy"]["status"] == "qualified"


@pytest.mark.parametrize("model,title", [
    ("2023 Zip-Up Workwear Denim Denim Jacket (TRR item LOU1175545)", "Louis Vuitton Zip-Up Workwear Denim Jacket"),
    ("Monogram Workwear Denim Jacket (size 56)", "Louis Vuitton Monogram Workwear Denim Jacket"),
    ("Monogram Workwear Jacket (Style 1AAGRP)", "Louis Vuitton Monogram Workwear Jacket"),
    ("2023 Zip-Up Workwear Denim Jacket", "Louis Vuitton Workwear Denim Jacket"),
])
def test_title_matching_ignores_catalog_size_year_and_extra_descriptors(model, title):
    assert source_title_supports(tokens("Louis Vuitton"), model, title)


@pytest.mark.parametrize("brand,model,title", [
    ("Louis Vuitton", "Denim Jacket", "Gucci Denim Jacket"),
    ("Louis Vuitton", "Monogram Denim Jacket", "Louis Vuitton"),
    ("Louis Vuitton", "Denim Jacket", "Louis Vuitton Leather Bag"),
])
def test_title_matching_preserves_brand_and_distinctive_names(brand, model, title):
    assert not source_title_supports(tokens(brand), model, title)


def summary_sample():
    data, raw = related_sample()
    data["grounding_sources"] = [{"url": URL, "snippet": "Barron Studded Leather Jacket — asking USD 600."}]
    raw = {"output": [{"type": "web_search_call", "action": {"type": "search", "sources": [{"url": URL}]}}]}
    return data, raw


def test_model_product_name_and_summary_pass_when_retrieved_url_has_no_title():
    data, raw = summary_sample()
    result = validate_valuation(data, IDENTITY, raw)
    assert result["pricing_evidence_policy"]["status"] == "qualified"
    assert result["pricing_evidence_policy"]["source_support"][URL] == "model_reported_summary_retrieved_url"


def test_model_summary_alone_without_provider_url_is_not_independent_evidence():
    data, raw = summary_sample()
    assert validate_valuation(data, IDENTITY, {})["pricing_evidence_policy"]["status"] == "needs_review"


def test_generated_summary_cannot_override_conflicting_native_title():
    data, raw = summary_sample()
    raw["output"][0]["action"]["sources"][0]["title"] = "John Varvatos Silk Shirt"
    assert validate_valuation(data, IDENTITY, raw)["pricing_evidence_policy"]["status"] == "needs_review"


def test_same_brand_similar_product_summary_can_use_different_model_name():
    data, raw = summary_sample()
    data["grounding_sources"][0]["snippet"] = "Alice Cooper Leather Biker — USD 600"
    assert validate_valuation(data, IDENTITY, raw)["pricing_evidence_policy"]["status"] == "qualified"


def test_summary_can_omit_descriptive_fabric_qualifier():
    data, raw = summary_sample()
    data["pricing_comparables"][0]["model"] += " (patchwork)"
    assert validate_valuation(data, IDENTITY, raw)["pricing_evidence_policy"]["status"] == "qualified"
