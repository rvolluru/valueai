from __future__ import annotations

from dataclasses import dataclass

from .types import BrandCandidate, OcrResult


EVIDENCE_PRIORITY = {
    "tag_label": 1.0,
    "logo_wordmark": 0.92,
    "hardware_engraving": 0.88,
    "hangtag": 0.84,
    "monogram_pattern": 0.75,
    "logo_classifier": 0.7,
}


@dataclass(slots=True)
class FusionThresholds:
    brand_accept_score: int = 78
    brand_accept_score_low: int = 70
    brand_gap_min: int = 8


@dataclass(slots=True)
class FusionDecision:
    name: str
    confidence: float
    evidence: str
    candidates: list[BrandCandidate]
    unknown: bool
    requested_photos: list[str]
    thresholds_used: dict[str, float]
    rationale: str


def score_ocr_candidate(
    match_score: float, ocr_conf: float, evidence_kind: str, agreement_count: int = 1
) -> float:
    evidence_weight = EVIDENCE_PRIORITY.get(evidence_kind, 0.8)
    agreement_boost = min(0.12, 0.04 * max(agreement_count - 1, 0))
    score = (0.7 * (match_score / 100.0) + 0.3 * ocr_conf) * evidence_weight + agreement_boost
    return max(0.0, min(score, 1.0))


def decide_brand(
    candidates: list[BrandCandidate],
    thresholds: FusionThresholds,
    ocr_results: list[OcrResult] | None = None,
) -> FusionDecision:
    ranked = sorted(candidates, key=lambda c: c.score, reverse=True)
    requested = []
    if not ranked:
        requested = ["close_up_tag_label", "close_up_logo_or_hardware"]
        return FusionDecision(
            name="unknown",
            confidence=0.0,
            evidence="insufficient_evidence",
            candidates=[],
            unknown=True,
            requested_photos=requested,
            thresholds_used={
                "BRAND_ACCEPT_SCORE": thresholds.brand_accept_score,
                "BRAND_ACCEPT_SCORE_LOW": thresholds.brand_accept_score_low,
                "BRAND_GAP_MIN": thresholds.brand_gap_min,
            },
            rationale="No brand candidates extracted from OCR/logo evidence.",
        )

    top = ranked[0]
    second = ranked[1] if len(ranked) > 1 else None
    gap = top.score - (second.score if second else 0)

    accept = False
    rationale = "below_threshold"
    if top.score >= thresholds.brand_accept_score:
        accept = True
        rationale = "top_score_high"
    elif top.score >= thresholds.brand_accept_score_low and gap >= thresholds.brand_gap_min:
        accept = True
        rationale = "top_score_low_with_gap"
    elif second and abs(gap) < thresholds.brand_gap_min:
        rationale = "contradictory_candidates"

    if not accept:
        requested = ["close_up_tag_label", "close_up_logo_or_hardware"]
        return FusionDecision(
            name="unknown",
            confidence=round(top.metadata.get("confidence_01", top.score / 100.0), 3),
            evidence="insufficient_evidence",
            candidates=ranked,
            unknown=True,
            requested_photos=requested,
            thresholds_used={
                "BRAND_ACCEPT_SCORE": thresholds.brand_accept_score,
                "BRAND_ACCEPT_SCORE_LOW": thresholds.brand_accept_score_low,
                "BRAND_GAP_MIN": thresholds.brand_gap_min,
            },
            rationale=rationale,
        )

    return FusionDecision(
        name=top.name,
        confidence=round(top.metadata.get("confidence_01", top.score / 100.0), 3),
        evidence=top.evidence,
        candidates=ranked,
        unknown=False,
        requested_photos=[],
        thresholds_used={
            "BRAND_ACCEPT_SCORE": thresholds.brand_accept_score,
            "BRAND_ACCEPT_SCORE_LOW": thresholds.brand_accept_score_low,
            "BRAND_GAP_MIN": thresholds.brand_gap_min,
        },
        rationale=rationale,
    )
