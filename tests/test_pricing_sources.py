import pytest

from app.gpt_item_profile import GptItemProfiler
from app.pricing_sources import RESALE_DOMAINS, allowed_domains, official_domains, url_in_domains
from app.pricing_evidence import validate_valuation


@pytest.mark.parametrize("url", [
    "https://therealreal.com/products/1", "https://www.ebay.co.uk/itm/1",
    "https://us.vestiairecollective.com/items/1", "https://www.vinted.fr/items/1",
])
def test_approved_sites_and_subdomains(url):
    assert url_in_domains(url, RESALE_DOMAINS)


@pytest.mark.parametrize("url", [
    "https://therealreal.com.evil.test/item", "https://eviltherealreal.com/item",
    "https://therealreal.com@evil.test/item", "https://user@therealreal.com/item",
    "https://therealreal.com:8080/item", "http://therealreal.com/item",
    "https://fashionphile.com/item", "https://nordstrom.com/item", "invalid",
])
def test_unapproved_or_deceptive_domains_rejected(url):
    assert not url_in_domains(url, RESALE_DOMAINS)


def test_brand_registry_uses_exact_identity_never_model_guessed_url():
    assert official_domains({"candidate_brand": "Louis Vuitton"}) == ("louisvuitton.com",)
    assert official_domains({"candidate_brand": "Hermès"}) == ("hermes.com",)
    assert official_domains({"candidate_brand": "Alice + Olivia"}) == ("aliceandolivia.com",)
    assert not official_domains({"candidate_brand": "Unknown", "official_website": "evil.test"})
    assert not official_domains({"candidate_brand": "Gucci collaboration Unknown"})
    assert "gucci.com" not in allowed_domains({"candidate_brand": "Prada"})


def test_legacy_trust_check_cannot_use_a_source_label_or_hostname_substring():
    profiler = GptItemProfiler.__new__(GptItemProfiler)
    assert not profiler._is_trusted_pricing_ref({"source": "therealreal.com", "url": "https://evil.test/item"})
    assert not profiler._is_trusted_pricing_ref({"url": "https://evil.test/therealreal.com"})
    assert profiler._is_trusted_pricing_ref({"url": "https://www.poshmark.com/listing/1"})


def test_pre_allowlist_policy_is_not_eligible_for_complete_analysis_reuse():
    from app.main import _cached_analysis_is_strong_enough_for_reuse
    cached = {"brand": {"name": "Prada", "confidence": .99},
        "item_profile": {"pricing_evidence_policy": {"version": "same-brand-comparables-v4", "status": "qualified"}}}
    assert not _cached_analysis_is_strong_enough_for_reuse(cached)


def test_api_filter_and_prompt_share_policy_even_with_override():
    profiler = GptItemProfiler.__new__(GptItemProfiler)
    profiler.openai_model = "gpt-5"
    profiler.reasoning_effort = "low"
    identity = {"candidate_brand": "Prada"}
    payload = profiler._build_openai_valuation_payload(content=[], gemini_profile=identity,
        valuation_prompt_override="Use any other website.")
    assert payload["tools"][0]["filters"]["allowed_domains"] == allowed_domains(identity)
    prompt = payload["input"][0]["content"][-1]["text"]
    assert "MANDATORY SOURCE RESTRICTIONS" in prompt and "prada.com" in prompt
    assert payload["model"] == "gpt-5"


def valuation(url, retail_url=None):
    row = dict(url=url, brand="Prada", model="Galleria Leather Bag", variant_match="confirmed",
        condition="LikeNew", price_type="asking", price=1000, currency="USD", match_type="exact",
        match_evidence="Brand and product match")
    data = dict(pricing_comparables=[row], resale_price_estimate=dict(estimated_price=900,
        references=[dict(url=url)]), retail_price_estimate=dict(estimated_price=3000,
        references=[dict(url=retail_url)] if retail_url else []))
    sources = [dict(url=url, title="Prada Galleria Leather Bag")]
    if retail_url:
        sources.append(dict(url=retail_url, title="Prada Galleria Leather Bag"))
    raw = dict(output=[dict(type="web_search_call", action=dict(sources=sources))])
    return data, raw


def test_approved_title_does_not_override_unapproved_site():
    data, raw = valuation("https://unapproved.test/item")
    result = validate_valuation(data, {"candidate_brand": "Prada", "candidate_model": "Galleria Leather Bag"}, raw)
    assert result["pricing_evidence_policy"]["rejected"][0]["reason"] == "unapproved_resale_source"
    assert result["resale_price_estimate"]["estimated_price"] is None


@pytest.mark.parametrize("retail_url,expected", [
    ("https://www.prada.com/product/1", 3000),
    ("https://gucci.com/product/1", None),
    ("https://www.therealreal.com/product/2", None),
    (None, None),
])
def test_retail_requires_identified_brand_site_without_blocking_resale(retail_url, expected):
    data, raw = valuation("https://www.therealreal.com/product/1", retail_url)
    result = validate_valuation(data, {"candidate_brand": "Prada", "candidate_model": "Galleria Leather Bag"}, raw)
    assert result["pricing_evidence_policy"]["status"] == "qualified"
    assert result["resale_price_estimate"]["estimated_price"] == 900
    assert result["retail_price_estimate"]["estimated_price"] == expected
