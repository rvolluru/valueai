from valuation.providers.rebag import RebagProvider


def test_rebag_provider_parses_shopify_meta_products() -> None:
    provider = RebagProvider()
    html = """
<script>
  window.ShopifyAnalytics = window.ShopifyAnalytics || {};
  window.ShopifyAnalytics.meta = window.ShopifyAnalytics.meta || {};
  var meta = {
    "products": [
      {
        "id": 7404433932465,
        "vendor": "Louis Vuitton",
        "type": "Totes",
        "handle": "handbags-louis-vuitton-neverfull-nm-tote-monogram-canvas-mm1925433",
        "variants": [
          {
            "id": 42420520059057,
            "price": 199500,
            "name": "Neverfull NM Tote Monogram Canvas MM - Neverfull NM Tote Monogram Canvas MM / brown",
            "public_title": "Neverfull NM Tote Monogram Canvas MM / brown",
            "sku": "192543/3"
          }
        ],
        "remote": false
      }
    ]
  };
</script>
""".strip()

    comps, meta = provider._parse(html)

    assert meta["shopify_products_count"] == 1
    assert len(comps) == 1
    assert comps[0].title == "Louis Vuitton Neverfull NM Tote Monogram Canvas MM"
    assert comps[0].price == 1995.0
    assert (
        comps[0].url
        == "https://shop.rebag.com/products/handbags-louis-vuitton-neverfull-nm-tote-monogram-canvas-mm1925433"
    )
    assert comps[0].metadata["parsed_from"] == "shopify_meta_products"
