from valuation.providers.poshmark import PoshmarkProvider


def test_parse_markdown_uses_listing_title_above_price_line() -> None:
    provider = PoshmarkProvider()
    markdown = """
[Louis Vuitton 1854 Neverfull MM Handbag](https://poshmark.com/listing/Louis-Vuitton-1854-Neverfull-MM-Handbag-62ba70eca4de41f100c693fe)

NWT

$3,465

[Size: OS](https://poshmark.com/category/Women-Bags?size=OS) [Louis Vuitton](https://poshmark.com/brand/Louis_Vuitton)
""".strip()

    comps, candidate_lines = provider._parse_markdown(markdown)

    assert candidate_lines == 1
    assert len(comps) == 1
    assert comps[0].title == "Louis Vuitton 1854 Neverfull MM Handbag"
    assert comps[0].price == 3465.0
    assert comps[0].url == (
        "https://poshmark.com/listing/Louis-Vuitton-1854-Neverfull-MM-Handbag-62ba70eca4de41f100c693fe"
    )
    assert comps[0].metadata["parsed_from"] == "firecrawl_markdown"


def test_parse_markdown_ignores_poshmark_ui_instruction_copy() -> None:
    provider = PoshmarkProvider()
    markdown = """
Select a category for specific sizes.

$20.50

[Louis Vuitton 1854 Neverfull MM Handbag](https://poshmark.com/listing/Louis-Vuitton-1854-Neverfull-MM-Handbag-62ba70eca4de41f100c693fe)

NWT

$3,465
""".strip()

    comps, candidate_lines = provider._parse_markdown(markdown)

    assert candidate_lines == 2
    assert len(comps) == 1
    assert comps[0].title == "Louis Vuitton 1854 Neverfull MM Handbag"
    assert comps[0].price == 3465.0


def test_parse_markdown_ignores_brand_and_category_links() -> None:
    provider = PoshmarkProvider()
    markdown = """
[Louis Vuitton](https://poshmark.com/brand/Louis_Vuitton)

$25

[Louis Vuitton 1854 Neverfull MM Handbag](https://poshmark.com/listing/Louis-Vuitton-1854-Neverfull-MM-Handbag-62ba70eca4de41f100c693fe)

$3,465
""".strip()

    comps, candidate_lines = provider._parse_markdown(markdown)

    assert candidate_lines == 2
    assert len(comps) == 1
    assert comps[0].title == "Louis Vuitton 1854 Neverfull MM Handbag"
    assert comps[0].price == 3465.0
