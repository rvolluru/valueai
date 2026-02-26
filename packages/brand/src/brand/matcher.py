from dataclasses import dataclass

from rapidfuzz import fuzz

from .brands import BrandRecord, alias_lookup
from .normalization import normalize_text


@dataclass(slots=True)
class MatchResult:
    candidate: str
    score: float
    source_text: str
    normalized_text: str
    method: str


class BrandMatcher:
    def __init__(self, records: list[BrandRecord]):
        self.records = records
        self._alias_map = alias_lookup(records)
        self._all_aliases: list[tuple[str, str]] = []
        for rec in records:
            alias_list = list(dict.fromkeys([rec.canonical, *rec.aliases]))
            for alias in alias_list:
                self._all_aliases.append((normalize_text(alias), rec.canonical))

    def match_text(self, text: str) -> list[MatchResult]:
        norm = normalize_text(text)
        if not norm:
            return []

        direct = self._alias_map.get(norm)
        if direct:
            return [
                MatchResult(
                    candidate=direct,
                    score=100.0,
                    source_text=text,
                    normalized_text=norm,
                    method="alias_exact",
                )
            ]

        best_by_candidate: dict[str, MatchResult] = {}
        for alias_norm, canonical in self._all_aliases:
            token_score = float(fuzz.token_set_ratio(norm, alias_norm))
            partial = float(fuzz.partial_ratio(norm, alias_norm))
            score = 0.6 * token_score + 0.4 * partial
            if score <= 0:
                continue
            existing = best_by_candidate.get(canonical)
            if existing is None or score > existing.score:
                best_by_candidate[canonical] = MatchResult(
                    candidate=canonical,
                    score=score,
                    source_text=text,
                    normalized_text=norm,
                    method="fuzzy",
                )

        return sorted(best_by_candidate.values(), key=lambda x: x.score, reverse=True)[:5]
