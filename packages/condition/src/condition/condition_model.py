from __future__ import annotations

from pathlib import Path

import numpy as np

from .types import ConditionIssue


GRADES = ["New", "LikeNew", "Good", "Fair", "Poor"]

ISSUE_MAP = {
    "clothes": ["stains", "pilling", "fading", "holes_tears", "fraying"],
    "shoes": ["scuffs", "creasing", "outsole_wear", "missing_laces"],
    "handbag": ["corner_wear", "hardware_scratches", "handle_wear", "lining_stain", "shape_loss"],
}


class ConditionModel:
    def __init__(self, weights_path: str | None = None):
        self.weights_path = weights_path
        self.available = bool(weights_path and Path(weights_path).exists())
        self._model = None
        if self.available:
            try:
                import timm  # type: ignore
                import torch  # type: ignore

                _ = timm, torch
                # TODO: load 5-way grade head + multi-label issue head.
                self._model = object()
            except Exception:
                self._model = None
                self.available = False

    def predict(self, crop: np.ndarray, category: str) -> tuple[str, float, list[ConditionIssue], dict]:
        if self._model is None:
            gray = crop.mean(axis=2) if crop.ndim == 3 else crop
            contrast = float(np.std(gray) / 255.0)
            grade = "Good"
            conf = 0.55 if contrast < 0.2 else 0.45
            issues: list[ConditionIssue] = []
            if category == "shoes":
                issues = [ConditionIssue(type="scuffs", severity="light")]
            elif category == "handbag":
                issues = [ConditionIssue(type="hardware_scratches", severity="light")]
            elif category == "clothes":
                issues = [ConditionIssue(type="pilling", severity="light")]
            return grade, round(conf, 3), issues, {
                "model": "stub_default",
                "contrast_estimate": round(contrast, 3),
                "probabilities": {
                    "New": 0.08,
                    "LikeNew": 0.18,
                    "Good": 0.46,
                    "Fair": 0.2,
                    "Poor": 0.08,
                },
            }

        # TODO: real model inference.
        return "Good", 0.4, [], {"model": "placeholder"}
