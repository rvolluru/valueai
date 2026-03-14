from valuation.providers.firecrawl_agent import FirecrawlAgentProvider
from valuation.providers.http_utils import build_search_query, query_for_request


def test_firecrawl_agent_normalizes_new_and_resale_medians_into_comps() -> None:
    provider = FirecrawlAgentProvider()
    comps = provider._normalize_result(
        {
            "item_name": "Gold Liquid Metal Leather Slingbacks with Jimmy Choo Perforated Corsage",
            "currency": "USD",
            "median_new_price_usd": 900.0,
            "median_resale_price_usd": 500.0,
            "new_comp_count": 5,
            "resale_comp_count": 8,
            "sources": [
                {
                    "title": "Jimmy Choo product page",
                    "price_usd": 900.0,
                    "condition": "new",
                    "url": "https://example.com/jimmy-choo",
                }
            ],
            "notes": "Structured market summary",
        }
    )

    assert len(comps) == 2
    resale = next(comp for comp in comps if comp.metadata["market_kind"] == "resale")
    retail = next(comp for comp in comps if comp.metadata["market_kind"] == "new")

    assert resale.source == "firecrawl_agent"
    assert resale.is_sold is True
    assert resale.price == 500.0
    assert retail.source == "firecrawl_agent"
    assert retail.is_sold is False
    assert retail.price == 900.0


def test_firecrawl_agent_extracts_google_result_entries_from_markdown() -> None:
    provider = FirecrawlAgentProvider()
    markdown = """
    [Gold Liquid Metal Leather Slingbacks With Jimmy Choo Perforated Corsage](https://us.jimmychoo.com/en/women/shoes/mimmi--sling-back-50/example.html)
    Jimmy Choo
    $1,150.00

    [Jimmy Choo Gold Liquid Metal Leather Sandals](https://poshmark.com/listing/example)
    Poshmark
    Pre-Owned
    $205

    [Jimmy Choo Rosalie Convertible Satchel](https://shop.rebag.com/products/handbags-example)
    Rebag
    $395
    """
    entries = provider._extract_entries(
        markdown,
        "Jimmy Choo Gold Liquid Metal Leather Slingbacks With Jimmy Choo Perforated Corsage shoes",
    )

    assert len(entries) == 2
    assert entries[0]["market_kind"] == "new"
    assert entries[0]["price_usd"] == 1150.0
    assert entries[1]["market_kind"] == "resale"
    assert entries[1]["price_usd"] == 205.0


def test_build_search_query_dedupes_repeated_title_parts() -> None:
    query = build_search_query(
        "Jimmy Choo",
        "Gold Liquid Metal Leather Slingbacks With Jimmy Choo Perforated Corsage",
        None,
        "Gold Liquid Metal Leather Slingbacks With Jimmy Choo Perforated Corsage",
        "shoes",
    )

    assert query == "Jimmy Choo Gold Liquid Metal Leather Slingbacks With Jimmy Choo Perforated Corsage shoes"


def test_query_for_request_keeps_item_description_when_title_hint_missing() -> None:
    query = query_for_request(
        "Jimmy Choo",
        "shoes",
        None,
        None,
        "Jimmy Choo Bing crystal mule",
    )

    assert query == "Jimmy Choo Bing crystal mule shoes"


def test_query_for_request_includes_size_when_provided() -> None:
    query = query_for_request(
        "Jimmy Choo",
        "shoes",
        None,
        None,
        "Jimmy Choo Bing crystal mule",
        "US 8.5",
    )

    assert query == "Jimmy Choo Bing crystal mule US 8.5 shoes"
