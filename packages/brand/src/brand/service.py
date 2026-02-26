from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from typing import Any

from .brands import load_brands
from .config import BrandConfig
from .evidence_detector import BrandEvidenceDetector
from .fusion import FusionThresholds, decide_brand, score_ocr_candidate
from .gpt_vision import GptVisionBrandClassifier
from .logo_classifier import LogoClassifier
from .matcher import BrandMatcher
from .types import BrandCandidate, ImageInput
from .ocr import OcrEngine


class BrandAnalyzer:
    def __init__(self, config: BrandConfig | None = None):
        self.config = config or BrandConfig()
        self.detector = BrandEvidenceDetector(weights_path=self.config.detector_weights_path)
        self.ocr = OcrEngine()
        self.records = load_brands()
        self.matcher = BrandMatcher(self.records)
        self.logo_classifier = LogoClassifier(
            enabled=self.config.enable_logo_classifier,
            weights_path=self.config.logo_classifier_weights_path,
        )
        self.gpt_vision = GptVisionBrandClassifier(
            enabled=self.config.enable_gpt_vision,
            api_key=self.config.openai_api_key,
            model=self.config.gpt_vision_model,
            timeout_s=self.config.gpt_vision_timeout_s,
        )

    def analyze(self, images: list[ImageInput], debug: bool = False) -> dict[str, Any]:
        boxes = self.detector.detect_brand_evidence(images)
        ocr_results = self.ocr.run(images, boxes)

        grouped: dict[str, list[BrandCandidate]] = defaultdict(list)
        evidence_lines: list[dict[str, Any]] = []
        agreement_count: dict[str, int] = defaultdict(int)

        for ocr_result in ocr_results:
            for line in ocr_result.lines:
                matches = self.matcher.match_text(line.text)
                cleaned = line.text.strip()
                filtered_matches = self._filter_matches_for_line(line.text, line.confidence, matches)
                evidence_lines.append(
                    {
                        "image_id": ocr_result.image_id,
                        "evidence_kind": ocr_result.evidence_kind,
                        "raw_text": line.text,
                        "cleaned_text": cleaned,
                        "ocr_confidence": round(line.confidence, 3),
                        "matches": [
                            {"name": m.candidate, "score": round(m.score, 1), "method": m.method}
                            for m in filtered_matches[:3]
                        ],
                    }
                )
                if not filtered_matches:
                    continue
                top = filtered_matches[0]
                agreement_count[top.candidate] += 1

        for ocr_result in ocr_results:
            for line in ocr_result.lines:
                matches = self.matcher.match_text(line.text)
                filtered_matches = self._filter_matches_for_line(line.text, line.confidence, matches)
                for m in filtered_matches[:3]:
                    conf01 = score_ocr_candidate(
                        match_score=m.score,
                        ocr_conf=line.confidence,
                        evidence_kind=ocr_result.evidence_kind,
                        agreement_count=agreement_count[m.candidate],
                    )
                    grouped[m.candidate].append(
                        BrandCandidate(
                            name=m.candidate,
                            score=round(conf01 * 100.0, 2),
                            evidence=self._evidence_label(ocr_result.evidence_kind),
                            metadata={
                                "confidence_01": round(conf01, 3),
                                "ocr_confidence": round(line.confidence, 3),
                                "match_score": round(m.score, 2),
                                "source_text": line.text,
                                "evidence_kind": ocr_result.evidence_kind,
                            },
                        )
                    )

        logo_out = self.logo_classifier.predict(images)
        for cand in logo_out.candidates:
            grouped[cand.name].append(cand)

        merged_candidates: list[BrandCandidate] = []
        for name, items in grouped.items():
            items = sorted(items, key=lambda c: c.score, reverse=True)
            top = items[0]
            avg_score = sum(i.score for i in items) / len(items)
            blended = 0.7 * top.score + 0.3 * avg_score
            merged_candidates.append(
                BrandCandidate(
                    name=name,
                    score=round(blended, 2),
                    evidence=top.evidence,
                    metadata={
                        **top.metadata,
                        "support_count": len(items),
                        "confidence_01": round(min(1.0, blended / 100.0), 3),
                    },
                )
            )

        thresholds = FusionThresholds(
            brand_accept_score=self.config.accept_score,
            brand_accept_score_low=self.config.accept_score_low,
            brand_gap_min=self.config.gap_min,
        )
        decision = decide_brand(merged_candidates, thresholds, ocr_results)
        gpt_vision_result = None
        if decision.unknown:
            gpt_vision_result = self.gpt_vision.classify(images, self.records)
            if gpt_vision_result.candidate:
                merged_with_vision = [*merged_candidates, gpt_vision_result.candidate]
                decision = decide_brand(merged_with_vision, thresholds, ocr_results)

        response: dict[str, Any] = {
            "name": decision.name,
            "confidence": decision.confidence,
            "evidence": decision.evidence,
        }
        debug_payload: dict[str, Any] = {
            "evidence_boxes": [asdict(b) for b in boxes],
            "ocr": evidence_lines,
            "brand_candidates": [
                {
                    "name": c.name,
                    "score": round(c.score, 2),
                    "evidence": c.evidence,
                    **({"metadata": c.metadata} if c.metadata else {}),
                }
                for c in decision.candidates
            ],
            "thresholds": decision.thresholds_used,
            "brand_rationale": decision.rationale,
            "ocr_backend": self.ocr.backend,
            "logo_classifier_enabled": self.config.enable_logo_classifier,
            "logo_classifier_model_available": logo_out.model_available,
            "gpt_vision": (
                {
                    "enabled": gpt_vision_result.enabled,
                    "called": gpt_vision_result.called,
                    "error": gpt_vision_result.error,
                    "candidate": (
                        {
                            "name": gpt_vision_result.candidate.name,
                            "score": gpt_vision_result.candidate.score,
                            "evidence": gpt_vision_result.candidate.evidence,
                            "metadata": gpt_vision_result.candidate.metadata,
                        }
                        if gpt_vision_result and gpt_vision_result.candidate
                        else None
                    ),
                }
                if gpt_vision_result
                else {
                    "enabled": self.config.enable_gpt_vision,
                    "called": False,
                    "error": None if self.config.enable_gpt_vision else "disabled",
                    "candidate": None,
                }
            ),
        }
        if debug or self.config.debug_default:
            response["candidates"] = debug_payload["brand_candidates"]
            response["_debug"] = debug_payload
        response["_requested_photos"] = decision.requested_photos
        return response

    @staticmethod
    def _filter_matches_for_line(text: str, ocr_conf: float, matches):
        cleaned = "".join(ch for ch in text if ch.isalnum())
        alpha_count = sum(ch.isalpha() for ch in cleaned)
        digit_count = sum(ch.isdigit() for ch in cleaned)
        length = len(cleaned)

        # Reject common OCR noise fragments before fuzzy brand matching.
        if length == 0:
            return []
        if ocr_conf < 0.12 and length <= 3:
            return []
        if digit_count > alpha_count and length <= 6:
            return []

        filtered = []
        for m in matches:
            if m.method == "alias_exact":
                filtered.append(m)
                continue
            min_score = 60.0 if length <= 3 else 55.0 if length <= 5 else 48.0
            if alpha_count <= 1:
                min_score = max(min_score, 70.0)
            if m.score >= min_score:
                filtered.append(m)
        return filtered

    @staticmethod
    def _evidence_label(kind: str) -> str:
        mapping = {
            "tag_label": "ocr_tag",
            "logo_wordmark": "ocr_logo",
            "hardware_engraving": "ocr_hardware",
            "hangtag": "ocr_hangtag",
            "monogram_pattern": "logo_classifier",
        }
        return mapping.get(kind, f"ocr_{kind}")
