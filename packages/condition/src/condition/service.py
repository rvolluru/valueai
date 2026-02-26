from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .category_classifier import CategoryClassifier
from .condition_model import ConditionModel
from .config import ConditionConfig
from .cropper import ProductCropper
from .types import ConditionResult


class ConditionAnalyzer:
    def __init__(self, config: ConditionConfig | None = None):
        self.config = config or ConditionConfig()
        self.cropper = ProductCropper(rembg_enabled=self.config.rembg_enabled)
        self.category_classifier = CategoryClassifier(self.config.category_model_weights_path)
        self.condition_model = ConditionModel(self.config.condition_model_weights_path)

    def analyze(
        self, primary_image: bytes, category_hint: str | None = None, debug: bool = False
    ) -> ConditionResult:
        crop, crop_meta = self.cropper.crop(primary_image)
        if category_hint:
            category, cat_conf, cat_meta = category_hint, 1.0, {"source": "user_provided"}
        else:
            category, cat_conf, cat_meta = self.category_classifier.predict(crop)
        grade, conf, issues, cond_meta = self.condition_model.predict(crop, category)
        debug_payload: dict[str, Any] = {
            "crop": crop_meta,
            "category": cat_meta,
            "condition": cond_meta,
        }
        return ConditionResult(
            category=category,
            category_confidence=cat_conf,
            grade=grade,
            confidence=conf,
            issues=issues,
            debug=debug_payload if debug else {},
        )

    @staticmethod
    def serialize(result: ConditionResult) -> dict[str, Any]:
        payload = {
            "grade": result.grade,
            "confidence": result.confidence,
            "issues": [asdict(i) for i in result.issues],
        }
        if result.debug:
            payload["_debug"] = result.debug
        return payload
