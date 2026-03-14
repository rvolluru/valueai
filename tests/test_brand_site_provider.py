from valuation.providers.brand_site import BrandSiteProvider, BrandSiteConfig
from valuation.types import ValuationRequest


def _req(grade: str = "New", brand: str = "Jimmy Choo") -> ValuationRequest:
    return ValuationRequest(
        brand=brand,
        brand_confidence=0.95,
        category="shoes",
        condition_grade=grade,
        condition_confidence=0.9,
        issues=[],
        title_hint="Gold Liquid Metal Leather Slingbacks",
    )


def test_brand_site_provider_skips_non_new_items() -> None:
    provider = BrandSiteProvider()

    comps = provider.fetch_comps(_req(grade="Good"))

    assert comps == []
    assert provider.last_debug["status"] == "skipped"
    assert provider.last_debug["reason"] == "condition_not_new"


def test_brand_site_provider_parses_markdown_listing() -> None:
    provider = BrandSiteProvider()
    config = BrandSiteConfig(
        site_name="Jimmy Choo",
        search_url_template="https://us.jimmychoo.com/en/search?q={query}",
        domain="us.jimmychoo.com",
    )
    markdown = """
[Gold Liquid Metal Leather Slingbacks](https://us.jimmychoo.com/en/shoes/gold-liquid-metal-leather-slingbacks/product123.html)

$1,295

[Search](https://us.jimmychoo.com/en/search?q=slingbacks)

$10
""".strip()

    comps, candidate_lines = provider._parse_markdown(markdown, config)

    assert candidate_lines == 2
    assert len(comps) == 1
    assert comps[0].title == "Gold Liquid Metal Leather Slingbacks"
    assert comps[0].price == 1295.0
    assert (
        comps[0].url
        == "https://us.jimmychoo.com/en/shoes/gold-liquid-metal-leather-slingbacks/product123.html"
    )
    assert comps[0].source == "brand_site"


def test_brand_site_provider_parses_json_ld_product() -> None:
    provider = BrandSiteProvider()
    config = BrandSiteConfig(
        site_name="Jimmy Choo",
        search_url_template="https://us.jimmychoo.com/en/search?q={query}",
        domain="us.jimmychoo.com",
    )
    html = """
<html>
  <head>
    <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "ProductGroup",
        "name": "Mimmi Sling Back 50",
        "url": "https://us.jimmychoo.com/en/women/mimmi--sling-back-50-MIMMISB50GXK.html",
        "hasVariant": [
          {
            "@type": "Product",
            "name": "Mimmi Sling Back 50",
            "offers": {
              "@type": "Offer",
              "price": "1150",
              "priceCurrency": "USD",
              "url": "https://us.jimmychoo.com/en/women/shoes/mimmi--sling-back-50/gold-liquid-metal-leather-slingbacks-with-jimmy-choo-perforated-corsage-J00018045134.html"
            }
          }
        ]
      }
    </script>
  </head>
</html>
""".strip()

    comps, meta = provider._parse_html(html, config)

    assert meta["json_ld_count"] == 1
    assert meta["next_data_found"] is False
    assert len(comps) == 1
    assert comps[0].title == "Gold Liquid Metal Leather Slingbacks With Jimmy Choo Perforated Corsage"
    assert comps[0].price == 1150.0
    assert (
        comps[0].url
        == "https://us.jimmychoo.com/en/women/shoes/mimmi--sling-back-50/gold-liquid-metal-leather-slingbacks-with-jimmy-choo-perforated-corsage-J00018045134.html"
    )
    assert comps[0].metadata["parsed_from"] == "json_ld"
