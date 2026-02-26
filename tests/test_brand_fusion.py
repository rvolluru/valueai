from brand.fusion import FusionThresholds, decide_brand
from brand.types import BrandCandidate


def _cand(name: str, score: float, evidence: str = "ocr_tag", conf01: float | None = None) -> BrandCandidate:
    return BrandCandidate(
        name=name,
        score=score,
        evidence=evidence,
        metadata={"confidence_01": conf01 if conf01 is not None else round(score / 100.0, 3)},
    )


def test_medium_threshold_accepts_high_score() -> None:
    decision = decide_brand([_cand("Nike", 82), _cand("Adidas", 60)], FusionThresholds())
    assert not decision.unknown
    assert decision.name == "Nike"
    assert decision.rationale == "top_score_high"


def test_medium_threshold_accepts_low_plus_gap() -> None:
    decision = decide_brand(
        [_cand("Nike", 72), _cand("Adidas", 61)],
        FusionThresholds(brand_accept_score=78, brand_accept_score_low=70, brand_gap_min=8),
    )
    assert not decision.unknown
    assert decision.name == "Nike"
    assert decision.rationale == "top_score_low_with_gap"


def test_medium_threshold_returns_unknown_when_gap_small() -> None:
    decision = decide_brand(
        [_cand("Nike", 73), _cand("Adidas", 69)],
        FusionThresholds(brand_accept_score=78, brand_accept_score_low=70, brand_gap_min=8),
    )
    assert decision.unknown
    assert decision.name == "unknown"
    assert "close_up_tag_label" in decision.requested_photos
    assert decision.rationale in {"contradictory_candidates", "below_threshold"}
