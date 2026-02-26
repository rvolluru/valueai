from brand.normalization import normalize_text


def test_normalize_text_unicode_case_punctuation_whitespace() -> None:
    assert normalize_text("  SéZane!!  Paris  ") == "sezane paris"
    assert normalize_text("Polo-Ralph   Lauren") == "polo ralph lauren"
