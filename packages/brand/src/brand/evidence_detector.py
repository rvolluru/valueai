from __future__ import annotations

from .types import EvidenceBox, ImageInput


EVIDENCE_KINDS = [
    "tag_label",
    "logo_wordmark",
    "hardware_engraving",
    "monogram_pattern",
    "hangtag",
]


class BrandEvidenceDetector:
    def __init__(self, weights_path: str | None = None):
        self.weights_path = weights_path
        self._detector = None
        if weights_path:
            try:
                from ultralytics import YOLO  # type: ignore

                self._detector = YOLO(weights_path)
            except Exception:
                self._detector = None

    def detect_brand_evidence(self, images: list[ImageInput]) -> list[EvidenceBox]:
        if self._detector:
            return self._detect_with_model(images)
        return self._fallback(images)

    def _detect_with_model(self, images: list[ImageInput]) -> list[EvidenceBox]:
        # TODO: implement YOLO inference when detector weights are trained and available.
        return self._fallback(images)

    def _fallback(self, images: list[ImageInput]) -> list[EvidenceBox]:
        boxes: list[EvidenceBox] = []
        for idx, image in enumerate(images):
            role = image.role_hint or ("full_item" if idx == 0 else "close_up")
            if role == "full_item":
                kind = "logo_wordmark"
            else:
                kind = "tag_label" if idx == 1 else "hardware_engraving"
            boxes.append(
                EvidenceBox(
                    image_id=image.image_id,
                    box_id=f"{image.image_id}:full",
                    kind=kind,
                    x1=0,
                    y1=0,
                    x2=1,
                    y2=1,
                    score=0.4,
                    fallback=True,
                )
            )
        return boxes
