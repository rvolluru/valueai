from __future__ import annotations

from dataclasses import dataclass


AGENT_VERSION = "trade-match-agent-mvp-1"


@dataclass(frozen=True)
class TradeMatchSuggestion:
    target_listing_id: str
    candidate_listing_id: str
    score: float
    confidence: float
    rationale: str
    risk_flags: list[str]
    agent_version: str = AGENT_VERSION


def _trade_match_tolerance(value: float) -> tuple[float, float]:
    v = float(value or 0.0)
    if v <= 0:
        return 0.0, 0.0
    if v < 250:
        pct = 0.30
    elif v < 500:
        pct = 0.25
    elif v < 1000:
        pct = 0.20
    elif v < 1500:
        pct = 0.15
    elif v < 3000:
        pct = 0.12
    elif v < 5000:
        pct = 0.10
    elif v < 10000:
        pct = 0.075
    else:
        pct = 0.05
    tolerance = v * pct
    if v >= 10000:
        tolerance = min(tolerance, 1000.0)
    return tolerance, pct


def _condition_rank(value: object) -> int:
    normalized = str(value or "").strip().casefold()
    if normalized == "new":
        return 2
    if normalized == "likenew":
        return 1
    return 0


def _clean(value: object) -> str:
    return str(value or "").strip()


def _same_owner(a: dict, b: dict) -> bool:
    a_subject = _clean(a.get("owner_subject"))
    b_subject = _clean(b.get("owner_subject"))
    if a_subject and b_subject and a_subject == b_subject:
        return True
    a_name = _clean(a.get("owner_name")).casefold()
    b_name = _clean(b.get("owner_name")).casefold()
    return bool(a_name and b_name and a_name == b_name)


def _has_image(listing: dict) -> bool:
    if _clean(listing.get("image")):
        return True
    images = listing.get("images")
    return isinstance(images, list) and any(_clean(x) for x in images)


def _profile_category_preferences(profile: dict | None) -> set[str]:
    raw = (profile or {}).get("category_preferences")
    if not isinstance(raw, list):
        return set()
    return {_clean(x).casefold() for x in raw if _clean(x)}


def build_trade_match_suggestions(
    *,
    viewer_subject: str,
    marketplace_listings: list[dict],
    viewer_active_listings: list[dict],
    viewer_profile: dict | None = None,
    max_matches_per_target: int = 3,
    max_total: int = 50,
) -> list[TradeMatchSuggestion]:
    """Build deterministic MVP suggestions without mutating app state."""
    prefs = _profile_category_preferences(viewer_profile)
    suggestions: list[TradeMatchSuggestion] = []

    for target in marketplace_listings:
        target_id = _clean(target.get("listing_id"))
        if not target_id:
            continue
        if _clean(target.get("owner_subject")) == viewer_subject:
            continue
        if _clean(target.get("status")).casefold() != "active":
            continue
        target_value = float(target.get("estimated_value") or 0)
        if target_value <= 0:
            continue
        tolerance, _ = _trade_match_tolerance(target_value)
        if tolerance <= 0:
            continue

        ranked_for_target: list[TradeMatchSuggestion] = []
        for candidate in viewer_active_listings:
            candidate_id = _clean(candidate.get("listing_id"))
            if not candidate_id or candidate_id == target_id:
                continue
            if _clean(candidate.get("status")).casefold() != "active":
                continue
            if _same_owner(target, candidate):
                continue
            candidate_value = float(candidate.get("estimated_value") or 0)
            if candidate_value <= 0:
                continue
            value_gap = abs(candidate_value - target_value)
            if value_gap > tolerance:
                continue

            target_category = _clean(target.get("category")).casefold()
            candidate_category = _clean(candidate.get("category")).casefold()
            value_fit = max(0.0, 1.0 - (value_gap / tolerance))
            score = value_fit * 55.0
            score += 15.0 if target_category == candidate_category else 6.0

            target_condition = _condition_rank(target.get("condition"))
            candidate_condition = _condition_rank(candidate.get("condition"))
            if candidate_condition >= target_condition and target_condition > 0:
                score += 10.0
            elif candidate_condition > 0:
                score += 6.0

            if not prefs or target_category in prefs:
                score += 8.0
            if _clean(target.get("brand")).casefold() == _clean(candidate.get("brand")).casefold():
                score += 5.0
            if _has_image(target) and _has_image(candidate):
                score += 7.0

            risk_flags: list[str] = []
            if value_gap > tolerance * 0.75:
                risk_flags.append("value_gap")
            if target_category != candidate_category:
                risk_flags.append("cross_category")
            if target_category in {"clothes", "shoes"}:
                risk_flags.append("size_sensitive")

            score = round(min(100.0, max(0.0, score)), 2)
            confidence = round(min(0.95, max(0.35, score / 100.0)), 2)
            value_text = f"${candidate_value:,.0f} vs ${target_value:,.0f}"
            category_text = "same category" if target_category == candidate_category else "cross-category"
            rationale = (
                f"{category_text} trade within value tolerance "
                f"({value_text}, gap ${value_gap:,.0f})."
            )
            ranked_for_target.append(
                TradeMatchSuggestion(
                    target_listing_id=target_id,
                    candidate_listing_id=candidate_id,
                    score=score,
                    confidence=confidence,
                    rationale=rationale,
                    risk_flags=risk_flags,
                )
            )

        ranked_for_target.sort(key=lambda item: item.score, reverse=True)
        for suggestion in ranked_for_target[: max(1, max_matches_per_target)]:
            suggestions.append(suggestion)

    suggestions.sort(key=lambda item: item.score, reverse=True)
    return suggestions[: max(1, max_total)]
