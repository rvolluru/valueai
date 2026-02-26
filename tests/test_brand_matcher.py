from brand.brands import BrandRecord
from brand.matcher import BrandMatcher


def test_alias_exact_mapping() -> None:
    matcher = BrandMatcher(
        [
            BrandRecord(canonical="Ralph Lauren", aliases=["polo ralph lauren"]),
            BrandRecord(canonical="Nike", aliases=[]),
        ]
    )
    matches = matcher.match_text("Polo Ralph Lauren")
    assert matches
    assert matches[0].candidate == "Ralph Lauren"
    assert matches[0].score == 100.0


def test_fuzzy_partial_match_prefers_nike() -> None:
    matcher = BrandMatcher(
        [
            BrandRecord(canonical="Nike", aliases=[]),
            BrandRecord(canonical="Nixon", aliases=[]),
        ]
    )
    matches = matcher.match_text("nike sportswear")
    assert matches[0].candidate == "Nike"
    assert matches[0].score >= matches[1].score
