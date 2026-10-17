import pytest

from app.pricing_evidence import source_title_supports, tokens, url_key, validate_valuation

BRAND = "Louis Vuitton"
MODEL = "Monogram Jacquard Fleece Zip-Through Jacket"
URL = "https://poshmark.com/listing/Louis-Vuitton-LV-Monogram-Jacquard-Fleece-ZipThrough-Jacket-Mens-Large-6abc1631a1bf20350ffabb19"


def sample(url=URL, model="LV Monogram Jacquard Fleece Zip\u2011Through Jacket", title=None):
    row = dict(url=url, brand=BRAND, model=model, variant_match="unconfirmed", condition="Good",
        price_type="asking", price=2400, currency="USD", match_type="exact",
        match_evidence="Product title matches this style; displayed asking price $2,400.",
        similarity_basis="Same named style; lower user condition.", adjustment_explanation="Condition adjustment explained.")
    data = dict(pricing_comparables=[row], resale_price_estimate=dict(estimated_price=3000,
        condition_grade="NewWithTags", references=[dict(url=url)]),
        retail_price_estimate=dict(estimated_price=None), resale_price_breakdown=[] ,
        grounding_sources=[dict(url=url, snippet="Exact style title; $2,400 asking; condition Good.")])
    source = dict(url=url)
    if title is not None:
        source["title"] = title
    raw = dict(output=[dict(type="web_search_call", action=dict(sources=[source]))])
    identity = dict(candidate_brand=BRAND, candidate_model=MODEL)
    return data, identity, raw


def test_latest_listing_short_summary_can_use_retrieved_product_slug():
    data, identity, raw = sample()
    result = validate_valuation(data, identity, raw)
    assert result["pricing_evidence_policy"]["status"] == "qualified"
    assert result["pricing_evidence_policy"]["source_support"][URL] == "retrieved_product_url_identity"


@pytest.mark.parametrize("model,title", [
    ("LV Monogram Jacquard Fleece Zip\u2011Through Jacket", "Louis Vuitton Monogram Fleece Jacket"),
    ("Men's Workwear Hooded Jacket Monogram Denim", "Louis Vuitton Mens Monogram Denim Workwear Hooded Jacket"),
    ("Monogram Denim Workwear Jacket (Beige, removable shearling collar)", "LV Monogram Denim Workwear Jacket"),
    ("Monogram Jacquard Fleece Jacket (2020)", "Louis Vuitton Monogram Fleece Jacket"),
])
def test_omitted_descriptors_possessives_aliases_and_hyphens_are_not_model_names(model, title):
    assert source_title_supports(tokens(BRAND), model, title)


def test_exact_claim_uses_same_unicode_and_sku_normalization():
    data, identity, raw = sample(model=MODEL.replace("-", "\u2011") + " (SKU 1A8ECV)")
    data["pricing_comparables"][0]["variant_match"] = "confirmed"
    assert validate_valuation(data, identity, raw)["pricing_evidence_policy"]["status"] == "qualified"


def test_brand_alias_is_scoped_to_established_brand():
    data, identity, raw = sample()
    data["pricing_comparables"][0]["brand"] = "LV"
    assert validate_valuation(data, identity, raw)["pricing_evidence_policy"]["status"] == "qualified"
    identity["candidate_brand"] = "Gucci"
    assert validate_valuation(data, identity, raw)["pricing_evidence_policy"]["status"] == "needs_review"


@pytest.mark.parametrize("title", ["Gucci Monogram Fleece Jacket", "Louis Vuitton Silk Shirt", "Louis Vuitton Leather Handbag"])
def test_native_brand_or_product_conflict_cannot_be_overridden_by_good_slug(title):
    data, identity, raw = sample(title=title)
    assert validate_valuation(data, identity, raw)["pricing_evidence_policy"]["status"] == "needs_review"


def test_generic_native_title_can_use_richer_product_url():
    data, identity, raw = sample(title="Louis Vuitton Fleece Jacket")
    assert validate_valuation(data, identity, raw)["pricing_evidence_policy"]["status"] == "qualified"


def test_same_brand_different_model_names_are_allowed():
    url = "https://www.therealreal.com/products/gucci-marmont-leather-bag"
    data, identity, raw = sample(url=url, model="Marmont Leather Bag", title="Gucci Dionysus Leather Bag")
    data["pricing_comparables"][0].update(brand="Gucci", match_type="related")
    identity.update(candidate_brand="Gucci", candidate_model="Marmont Leather Bag")
    assert validate_valuation(data, identity, raw)["pricing_evidence_policy"]["status"] == "qualified"


def test_same_brand_different_model_numbers_are_allowed():
    data, identity, raw = sample(url="https://www.therealreal.com/products/prada-re-edition-2005-bag",
        model="Re Edition 2005 Bag", title="Prada Re Edition 2000 Bag")
    data["pricing_comparables"][0].update(brand="Prada", match_type="related")
    identity.update(candidate_brand="Prada", candidate_model="Re Edition 2005 Bag")
    assert validate_valuation(data, identity, raw)["pricing_evidence_policy"]["status"] == "qualified"


def test_shortened_exact_claim_becomes_supported_related_comparable():
    data, identity, raw = sample(model="Monogram Jacquard Fleece Jacket (2020)",
        title="Louis Vuitton Monogram Fleece Jacket")
    data["pricing_comparables"][0]["variant_match"] = "confirmed"
    result = validate_valuation(data, identity, raw)
    policy = result["pricing_evidence_policy"]
    assert policy["status"] == "qualified"
    assert policy["basis"] == "same_brand_similar_model"
    assert policy["accepted"][0]["match_type"] == "related"
    assert data["pricing_comparables"][0]["match_type"] == "exact"


def test_nonliteral_exact_claim_requires_similarity_and_adjustment_context():
    data, identity, raw = sample(model="Monogram Fleece Jacket", title="Louis Vuitton Fleece Jacket")
    data["pricing_comparables"][0].update(variant_match="confirmed", adjustment_explanation="")
    assert validate_valuation(data, identity, raw)["pricing_evidence_policy"]["status"] == "needs_review"


def test_same_brand_wrong_product_family_cannot_be_an_anchor():
    data, identity, raw = sample(model="Silk Dress", title="Louis Vuitton Silk Dress")
    assert validate_valuation(data, identity, raw)["pricing_evidence_policy"]["status"] == "needs_review"


def test_retrieved_brand_only_url_and_generic_summary_are_not_enough():
    data, identity, raw = sample(url="https://poshmark.com/listing/louis-vuitton-123")
    assert validate_valuation(data, identity, raw)["pricing_evidence_policy"]["status"] == "needs_review"


def test_unretrieved_model_url_is_not_enough():
    data, identity, raw = sample()
    assert validate_valuation(data, identity, {})["pricing_evidence_policy"]["status"] == "needs_review"


def test_query_keywords_do_not_count_as_product_identity():
    data, identity, raw = sample(url="https://poshmark.com/listing/123?q=Louis-Vuitton-Monogram-Jacquard-Fleece-ZipThrough-Jacket")
    assert validate_valuation(data, identity, raw)["pricing_evidence_policy"]["status"] == "needs_review"


def test_tracking_parameters_do_not_hide_retrieved_url():
    data, identity, raw = sample()
    raw["output"][0]["action"]["sources"][0]["url"] += "?utm_source=openai&fbclid=tracking"
    assert validate_valuation(data, identity, raw)["pricing_evidence_policy"]["status"] == "qualified"
    assert url_key("https://example.com/item?id=42&utm_source=openai") == "https://example.com/item?id=42"


def test_latest_shadow_ebay_tracking_is_not_a_different_product():
    data, identity, raw = sample(url="https://www.ebay.com/itm/198596669531",
        model="Monogram Teddy/Monogram Jacquard Fleece Jacket (navy/charcoal)")
    data["pricing_comparables"][0]["match_type"] = "related"
    data["grounding_sources"][0]["snippet"] = "Sold Louis Vuitton Monogram teddy fleece jacket in navy/charcoal at $1,300."
    raw["output"][0]["action"]["sources"][0]["url"] += "?itmmeta=tracking&itmprp=campaign"
    assert validate_valuation(data, identity, raw)["pricing_evidence_policy"]["status"] == "qualified"
    assert url_key("https://www.ebay.com/itm/198596669531?var=123&itmmeta=tracking") == "https://www.ebay.com/itm/198596669531?var=123"


@pytest.mark.parametrize("field,value", [("price", 0), ("currency", "EUR"), ("price_type", "retail"), ("match_evidence", "")])
def test_identity_relaxation_does_not_bypass_other_price_checks(field, value):
    data, identity, raw = sample()
    data["pricing_comparables"][0][field] = value
    assert validate_valuation(data, identity, raw)["pricing_evidence_policy"]["status"] == "needs_review"
