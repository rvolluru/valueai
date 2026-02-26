from __future__ import annotations

from dataclasses import dataclass

from .types import BrandCandidate, ImageInput


@dataclass(slots=True)
class LogoClassifierOutput:
    candidates: list[BrandCandidate]
    model_available: bool


class LogoClassifier:
    def __init__(self, enabled: bool = False, weights_path: str | None = None):
        self.enabled = enabled
        self.weights_path = weights_path
        self._model = None
        if enabled and weights_path:
            try:
                import timm  # type: ignore
                import torch  # type: ignore

                _ = timm, torch
                # TODO: load finetuned 200-way head and class index mapping.
                self._model = object()
            except Exception:
                self._model = None

    def predict(self, images: list[ImageInput]) -> LogoClassifierOutput:
        if not self.enabled or self._model is None:
            return LogoClassifierOutput(candidates=[], model_available=False)
        # TODO: implement inference using timm backbone + finetuned head.
        return LogoClassifierOutput(candidates=[], model_available=True)
