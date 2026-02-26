from __future__ import annotations

from pathlib import Path

import numpy as np


CATEGORIES = ["clothes", "shoes", "handbag"]


class CategoryClassifier:
    def __init__(self, weights_path: str | None = None):
        self.weights_path = weights_path
        self.available = bool(weights_path and Path(weights_path).exists())
        self._model = None
        if self.available:
            try:
                import timm  # type: ignore
                import torch  # type: ignore

                _ = timm, torch
                # TODO: load finetuned 3-way category classifier weights.
                self._model = object()
            except Exception:
                self._model = None
                self.available = False

    def predict(self, crop: np.ndarray) -> tuple[str, float, dict]:
        if self._model is None:
            h, w = crop.shape[:2]
            ratio = w / max(h, 1)
            category = "shoes" if ratio > 1.35 else "handbag" if ratio > 0.9 else "clothes"
            return category, 0.42, {"model": "stub_heuristic", "w_h_ratio": round(ratio, 3)}
        # TODO: implement timm inference.
        return "clothes", 0.33, {"model": "placeholder"}
